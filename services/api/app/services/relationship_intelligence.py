from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    ActionItem,
    Deal,
    DealParticipant,
    DerivedDocumentContent,
    Document,
    EntityMention,
    Interaction,
    InteractionParticipant,
    RelationshipEntity,
    RelationshipEvidence,
    RelationshipRole,
)


@dataclass(frozen=True)
class EntitySignal:
    name: str
    entity_type: str
    roles: tuple[str, ...]
    confidence: float
    excerpt: str


@dataclass(frozen=True)
class InteractionSignal:
    title: str
    interaction_type: str
    summary: str
    occurred_at: datetime | None
    confidence: float
    excerpt: str


@dataclass(frozen=True)
class ActionSignal:
    title: str
    priority: str
    due_at: datetime | None
    confidence: float
    excerpt: str


@dataclass(frozen=True)
class DealSignal:
    name: str
    deal_type: str
    stage: str
    amount: Decimal | None
    currency: str | None
    summary: str
    confidence: float
    excerpt: str


@dataclass(frozen=True)
class RelationshipSignals:
    entities: list[EntitySignal]
    interactions: list[InteractionSignal]
    actions: list[ActionSignal]
    deals: list[DealSignal]


COMPANY_SUFFIX_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&.,' -]{1,80}?\s(?:"
    r"Capital|Ventures|Partners|Partner|Fund|Funds|Advisors|Advisor|Bank|Group|Holdings|"
    r"Limited|Ltd|Pvt Ltd|Private Limited|Inc|Corp|Corporation|Technologies|Technology|"
    r"Finance|Financial|Securities|Asset Management|Management|Labs|Systems"
    r"))\b"
)
PERSON_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
AMOUNT_RE = re.compile(
    r"(?P<currency>USD|US\$|\$|INR|Rs\.?|₹|EUR|GBP)?\s*"
    r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>m|mn|million|cr|crore|bn|billion)?",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Z][a-z]+\s+\d{4})\b")

INVESTOR_HINTS = {
    "capital",
    "ventures",
    "partners",
    "partner",
    "fund",
    "funds",
    "asset management",
    "securities",
}
CLIENT_HINTS = {"client", "mandate", "company", "founder", "management", "sell-side", "buy-side"}
DEAL_HINTS = {
    "fundraise": "capital_raise",
    "fund raise": "capital_raise",
    "raise": "capital_raise",
    "series": "capital_raise",
    "sell-side": "sell_side",
    "sell side": "sell_side",
    "buy-side": "buy_side",
    "buy side": "buy_side",
    "mandate": "mandate",
    "acquisition": "m_and_a",
    "m&a": "m_and_a",
    "merger": "m_and_a",
}
ACTION_PREFIX_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:action item|action|todo|to do|next step|follow[- ]?up|follow up)\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)


def process_document_relationship_intelligence(
    db: Session,
    *,
    document: Document,
    text: str,
    source_type: str | None = None,
) -> dict[str, int]:
    signals = extract_relationship_signals(
        text,
        title=document.name,
        source_type=source_type or _source_type(document),
        created_at=document.created_at,
    )
    return upsert_relationship_signals(
        db,
        organization_id=document.organization_id,
        signals=signals,
        source_type=source_type or _source_type(document),
        source_url=document.source_url,
        document_id=document.id,
        connector_item_id=None,
        source_title=document.name,
        source_metadata={
            "document_id": str(document.id),
            "knowledge_base_id": str(document.knowledge_base_id),
            "document_name": document.name,
            "document_tags": document.tags,
            "document_confidentiality": document.confidentiality.value,
            "source": "document_pipeline",
        },
    )


def rescan_relationship_intelligence(
    db: Session,
    *,
    organization_id: UUID,
    document_ids: list[UUID] | None = None,
) -> dict[str, int]:
    query = select(Document).where(
        Document.organization_id == organization_id,
        Document.deleted_at.is_(None),
    )
    if document_ids:
        query = query.where(Document.id.in_(document_ids))
    totals = {"entities": 0, "interactions": 0, "actions": 0, "deals": 0}
    for document in db.scalars(query.order_by(Document.updated_at.desc())):
        text = _latest_document_text(db, document)
        if not text.strip():
            continue
        result = process_document_relationship_intelligence(db, document=document, text=text)
        totals = {key: totals[key] + result.get(key, 0) for key in totals}
    db.commit()
    return totals


def extract_relationship_signals(
    text: str,
    *,
    title: str = "",
    source_type: str = "document",
    created_at: datetime | None = None,
) -> RelationshipSignals:
    clean = _clean_text(text)
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    entities = _dedupe_entities(
        [
            *_entity_signals_from_labels(lines),
            *_entity_signals_from_suffixes(clean),
            *_person_signals(lines, clean),
            *_email_contact_signals(clean),
        ]
    )
    interactions = _interaction_signals(lines, title, source_type, created_at)
    actions = _action_signals(lines)
    deals = _deal_signals(clean, title, entities)
    return RelationshipSignals(entities=entities, interactions=interactions, actions=actions, deals=deals)


def upsert_relationship_signals(
    db: Session,
    *,
    organization_id: UUID,
    signals: RelationshipSignals,
    source_type: str,
    source_url: str | None,
    document_id: UUID | None,
    connector_item_id: UUID | None,
    source_title: str,
    source_metadata: dict[str, Any],
) -> dict[str, int]:
    entity_by_key: dict[tuple[str, str], RelationshipEntity] = {}
    for signal in signals.entities:
        entity = _upsert_entity(db, organization_id, signal, source_metadata)
        entity_by_key[(_normalize(signal.name), signal.entity_type)] = entity
        _upsert_roles(db, organization_id, entity, signal.roles, signal.confidence, source_metadata)
        _record_entity_evidence(
            db,
            organization_id=organization_id,
            entity=entity,
            document_id=document_id,
            connector_item_id=connector_item_id,
            field_name="mention",
            source_type=source_type,
            source_url=source_url,
            excerpt=signal.excerpt,
            confidence=signal.confidence,
            metadata=source_metadata,
        )

    primary_entity = _primary_entity(entity_by_key)
    interactions = []
    for signal in signals.interactions:
        interaction = _upsert_interaction(
            db,
            organization_id=organization_id,
            signal=signal,
            source_type=source_type,
            source_url=source_url,
            document_id=document_id,
            connector_item_id=connector_item_id,
            source_title=source_title,
            metadata=source_metadata,
        )
        interactions.append(interaction)
        for entity in entity_by_key.values():
            _upsert_interaction_participant(db, organization_id, interaction, entity, "mentioned")
            _refresh_last_interaction(entity, signal.occurred_at or interaction.created_at)
        _record_generic_evidence(
            db,
            organization_id=organization_id,
            field_name="interaction",
            source_type=source_type,
            source_url=source_url,
            excerpt=signal.excerpt,
            confidence=signal.confidence,
            metadata=source_metadata,
            document_id=document_id,
            connector_item_id=connector_item_id,
            interaction_id=interaction.id,
        )

    primary_interaction = interactions[0] if interactions else None
    deals = []
    for signal in signals.deals:
        deal = _upsert_deal(db, organization_id, signal, primary_entity, source_metadata)
        deals.append(deal)
        if primary_entity:
            _upsert_deal_participant(db, organization_id, deal, primary_entity, "company")
        for entity in entity_by_key.values():
            if entity.id != getattr(primary_entity, "id", None):
                _upsert_deal_participant(db, organization_id, deal, entity, _deal_role_for_entity(entity))
        _record_generic_evidence(
            db,
            organization_id=organization_id,
            field_name="deal",
            source_type=source_type,
            source_url=source_url,
            excerpt=signal.excerpt,
            confidence=signal.confidence,
            metadata=source_metadata,
            document_id=document_id,
            connector_item_id=connector_item_id,
            deal_id=deal.id,
        )

    primary_deal = deals[0] if deals else None
    for signal in signals.actions:
        action = _upsert_action_item(
            db,
            organization_id=organization_id,
            signal=signal,
            entity=primary_entity,
            deal=primary_deal,
            interaction=primary_interaction,
            source_type=source_type,
            metadata=source_metadata,
        )
        if primary_entity and (not primary_entity.next_action_at or (signal.due_at and signal.due_at < primary_entity.next_action_at)):
            primary_entity.next_action_at = signal.due_at
        _record_generic_evidence(
            db,
            organization_id=organization_id,
            field_name="action_item",
            source_type=source_type,
            source_url=source_url,
            excerpt=signal.excerpt,
            confidence=signal.confidence,
            metadata=source_metadata,
            document_id=document_id,
            connector_item_id=connector_item_id,
            action_item_id=action.id,
        )

    return {
        "entities": len(signals.entities),
        "interactions": len(signals.interactions),
        "actions": len(signals.actions),
        "deals": len(signals.deals),
    }


def _entity_signals_from_labels(lines: list[str]) -> list[EntitySignal]:
    signals = []
    label_re = re.compile(
        r"^\s*(client|company|investor|fund|founder|management|attendees?|participants?|contacts?)\s*[:\-]\s*(.+)$",
        re.IGNORECASE,
    )
    for line in lines:
        match = label_re.match(line)
        if not match:
            continue
        label = match.group(1).lower()
        values = _split_names(match.group(2))
        for value in values:
            entity_type, roles = _classify_label_value(label, value, line)
            if value and not _is_noise_name(value):
                signals.append(EntitySignal(value, entity_type, roles, 0.82, line[:700]))
    return signals


def _entity_signals_from_suffixes(text: str) -> list[EntitySignal]:
    signals = []
    for match in COMPANY_SUFFIX_RE.finditer(text):
        name = _clean_name(match.group(1))
        if not name or _is_noise_name(name):
            continue
        entity_type = "investor" if _looks_like_investor(name, _context(text, match.start())) else "company"
        roles = ("investor",) if entity_type == "investor" else ("prospective_client",)
        signals.append(EntitySignal(name, entity_type, roles, 0.74, _context(text, match.start())))
    return signals


def _person_signals(lines: list[str], text: str) -> list[EntitySignal]:
    signals = []
    person_lines = [
        line
        for line in lines
        if re.search(r"\b(attendee|participant|founder|ceo|cfo|contact|met with|introduced by)\b", line, re.IGNORECASE)
    ]
    for line in person_lines:
        for match in PERSON_RE.finditer(line):
            name = _clean_name(match.group(1))
            if name and not _is_noise_name(name) and not _looks_like_company(name):
                signals.append(EntitySignal(name, "person", _person_roles(line), 0.68, line[:700]))
    for email in EMAIL_RE.findall(text):
        local = email.split("@", 1)[0].replace(".", " ").replace("_", " ").replace("-", " ")
        name = " ".join(part.capitalize() for part in local.split() if part)
        if len(name.split()) >= 2:
            signals.append(EntitySignal(name, "person", ("contact",), 0.55, email))
    return signals


def _email_contact_signals(text: str) -> list[EntitySignal]:
    signals = []
    for email in EMAIL_RE.findall(text):
        domain = email.split("@", 1)[1].split(".", 1)[0]
        name = _clean_name(domain.replace("-", " ").title())
        if len(name) > 2:
            signals.append(EntitySignal(name, "company", ("contact_domain",), 0.45, email))
    return signals


def _interaction_signals(
    lines: list[str],
    title: str,
    source_type: str,
    created_at: datetime | None,
) -> list[InteractionSignal]:
    haystack = f"{title}\n" + "\n".join(lines[:12])
    interaction_words = r"\b(meeting|call|discussion|minutes|notes|granola|transcript|attendees|participants)\b"
    if not re.search(interaction_words, haystack, re.IGNORECASE) and source_type not in {"granola", "telegram"}:
        return []
    occurred_at = _parse_first_date(haystack) or created_at
    summary = _summary_from_lines(lines, fallback=title)
    interaction_type = "meeting" if re.search(r"\b(meeting|granola|transcript|attendees)\b", haystack, re.IGNORECASE) else "note"
    return [
        InteractionSignal(
            title=title or "Relationship note",
            interaction_type=interaction_type,
            summary=summary,
            occurred_at=occurred_at,
            confidence=0.78,
            excerpt="\n".join(lines[:8])[:900],
        )
    ]


def _action_signals(lines: list[str]) -> list[ActionSignal]:
    signals = []
    for line in lines:
        match = ACTION_PREFIX_RE.match(line)
        if match:
            title = _clean_action(match.group(1))
            if title:
                signals.append(ActionSignal(title, _priority(line), _parse_first_date(line), 0.82, line[:700]))
                continue
        if re.search(r"\b(follow up|send|share|schedule|prepare|circulate|introduce|confirm)\b", line, re.IGNORECASE):
            if re.match(r"^\s*[-*]\s+", line):
                title = _clean_action(re.sub(r"^\s*[-*]\s+", "", line))
                signals.append(ActionSignal(title, _priority(line), _parse_first_date(line), 0.62, line[:700]))
    return _dedupe_actions(signals)


def _deal_signals(text: str, title: str, entities: list[EntitySignal]) -> list[DealSignal]:
    lowered = text.lower()
    matched_type = next((deal_type for hint, deal_type in DEAL_HINTS.items() if hint in lowered), None)
    if not matched_type:
        return []
    amount, currency = _first_amount(text)
    company = next((entity.name for entity in entities if entity.entity_type == "company"), None)
    name = f"{company or title or 'Relationship'} {matched_type.replace('_', ' ').title()}"
    stage = _stage_from_text(lowered)
    excerpt = _context(text, lowered.find(next(hint for hint in DEAL_HINTS if hint in lowered)))
    return [
        DealSignal(
            name=name[:260],
            deal_type=matched_type,
            stage=stage,
            amount=amount,
            currency=currency,
            summary=_summary_from_text(text),
            confidence=0.7 if amount else 0.62,
            excerpt=excerpt,
        )
    ]


def _upsert_entity(
    db: Session,
    organization_id: UUID,
    signal: EntitySignal,
    source_metadata: dict[str, Any],
) -> RelationshipEntity:
    normalized = _normalize(signal.name)
    entity = db.scalar(
        select(RelationshipEntity).where(
            RelationshipEntity.organization_id == organization_id,
            RelationshipEntity.normalized_name == normalized,
            RelationshipEntity.entity_type == signal.entity_type,
            RelationshipEntity.deleted_at.is_(None),
        )
    )
    if not entity:
        entity = RelationshipEntity(
            organization_id=organization_id,
            name=signal.name,
            normalized_name=normalized,
            entity_type=signal.entity_type,
            confidence=signal.confidence,
            summary=_signal_summary(signal),
            status="suggested",
            metadata_json={"sources": [source_metadata]},
        )
        db.add(entity)
        db.flush()
    else:
        entity.confidence = max(float(entity.confidence or 0), signal.confidence)
        entity.summary = entity.summary or _signal_summary(signal)
        entity.metadata_json = _append_source(entity.metadata_json, source_metadata)
    db.add(
        EntityMention(
            organization_id=organization_id,
            relationship_entity_id=entity.id,
            document_id=_uuid_from_metadata(source_metadata, "document_id"),
            mention_text=signal.name,
            normalized_mention=normalized,
            context=signal.excerpt,
            confidence=signal.confidence,
        )
    )
    return entity


def _upsert_roles(
    db: Session,
    organization_id: UUID,
    entity: RelationshipEntity,
    roles: tuple[str, ...],
    confidence: float,
    metadata: dict[str, Any],
) -> None:
    for role in roles:
        existing = db.scalar(
            select(RelationshipRole).where(
                RelationshipRole.relationship_entity_id == entity.id,
                RelationshipRole.role_name == role,
            )
        )
        if existing:
            existing.confidence = max(float(existing.confidence or 0), confidence)
            continue
        db.add(
            RelationshipRole(
                organization_id=organization_id,
                relationship_entity_id=entity.id,
                role_name=role,
                confidence=confidence,
                metadata_json=metadata,
            )
        )


def _upsert_interaction(
    db: Session,
    *,
    organization_id: UUID,
    signal: InteractionSignal,
    source_type: str,
    source_url: str | None,
    document_id: UUID | None,
    connector_item_id: UUID | None,
    source_title: str,
    metadata: dict[str, Any],
) -> Interaction:
    existing = None
    if document_id:
        existing = db.scalar(
            select(Interaction).where(
                Interaction.organization_id == organization_id,
                Interaction.document_id == document_id,
                Interaction.title == signal.title[:300],
            )
        )
    if existing:
        existing.summary = signal.summary or existing.summary
        existing.occurred_at = signal.occurred_at or existing.occurred_at
        return existing
    interaction = Interaction(
        organization_id=organization_id,
        title=(signal.title or source_title or "Relationship note")[:300],
        interaction_type=signal.interaction_type,
        occurred_at=signal.occurred_at,
        source_type=source_type,
        source_url=source_url,
        document_id=document_id,
        connector_item_id=connector_item_id,
        summary=signal.summary,
        status="suggested",
        metadata_json=metadata,
    )
    db.add(interaction)
    db.flush()
    return interaction


def _upsert_interaction_participant(
    db: Session,
    organization_id: UUID,
    interaction: Interaction,
    entity: RelationshipEntity,
    role: str,
) -> None:
    existing = db.scalar(
        select(InteractionParticipant).where(
            InteractionParticipant.interaction_id == interaction.id,
            InteractionParticipant.relationship_entity_id == entity.id,
            InteractionParticipant.role_name == role,
        )
    )
    if not existing:
        db.add(
            InteractionParticipant(
                organization_id=organization_id,
                interaction_id=interaction.id,
                relationship_entity_id=entity.id,
                role_name=role,
            )
        )


def _upsert_deal(
    db: Session,
    organization_id: UUID,
    signal: DealSignal,
    company: RelationshipEntity | None,
    metadata: dict[str, Any],
) -> Deal:
    query = select(Deal).where(
        Deal.organization_id == organization_id,
        Deal.name == signal.name,
        Deal.deleted_at.is_(None),
    )
    existing = db.scalar(query)
    if existing:
        existing.stage = signal.stage or existing.stage
        existing.amount = signal.amount or existing.amount
        existing.currency = signal.currency or existing.currency
        existing.confidence = max(float(existing.confidence or 0), signal.confidence)
        return existing
    deal = Deal(
        organization_id=organization_id,
        name=signal.name,
        deal_type=signal.deal_type,
        stage=signal.stage,
        company_entity_id=company.id if company else None,
        amount=signal.amount,
        currency=signal.currency,
        summary=signal.summary,
        confidence=signal.confidence,
        status="suggested",
        metadata_json=metadata,
    )
    db.add(deal)
    db.flush()
    return deal


def _upsert_deal_participant(
    db: Session,
    organization_id: UUID,
    deal: Deal,
    entity: RelationshipEntity,
    role: str,
) -> None:
    existing = db.scalar(
        select(DealParticipant).where(
            DealParticipant.deal_id == deal.id,
            DealParticipant.relationship_entity_id == entity.id,
            DealParticipant.role_name == role,
        )
    )
    if not existing:
        db.add(
            DealParticipant(
                organization_id=organization_id,
                deal_id=deal.id,
                relationship_entity_id=entity.id,
                role_name=role,
            )
        )


def _upsert_action_item(
    db: Session,
    *,
    organization_id: UUID,
    signal: ActionSignal,
    entity: RelationshipEntity | None,
    deal: Deal | None,
    interaction: Interaction | None,
    source_type: str,
    metadata: dict[str, Any],
) -> ActionItem:
    existing = db.scalar(
        select(ActionItem).where(
            ActionItem.organization_id == organization_id,
            func.lower(ActionItem.title) == signal.title.lower(),
            ActionItem.status.in_(["open", "suggested"]),
        )
    )
    if existing:
        existing.relationship_entity_id = existing.relationship_entity_id or (entity.id if entity else None)
        existing.deal_id = existing.deal_id or (deal.id if deal else None)
        existing.interaction_id = existing.interaction_id or (interaction.id if interaction else None)
        existing.due_at = signal.due_at or existing.due_at
        existing.confidence = max(float(existing.confidence or 0), signal.confidence)
        return existing
    action = ActionItem(
        organization_id=organization_id,
        title=signal.title[:300],
        description=signal.excerpt,
        relationship_entity_id=entity.id if entity else None,
        deal_id=deal.id if deal else None,
        interaction_id=interaction.id if interaction else None,
        due_at=signal.due_at,
        priority=signal.priority,
        status="open",
        source_type=source_type,
        confidence=signal.confidence,
        metadata_json=metadata,
    )
    db.add(action)
    db.flush()
    return action


def _record_entity_evidence(
    db: Session,
    *,
    organization_id: UUID,
    entity: RelationshipEntity,
    document_id: UUID | None,
    connector_item_id: UUID | None,
    field_name: str,
    source_type: str,
    source_url: str | None,
    excerpt: str,
    confidence: float,
    metadata: dict[str, Any],
) -> None:
    _record_generic_evidence(
        db,
        organization_id=organization_id,
        relationship_entity_id=entity.id,
        document_id=document_id,
        connector_item_id=connector_item_id,
        field_name=field_name,
        source_type=source_type,
        source_url=source_url,
        excerpt=excerpt,
        confidence=confidence,
        metadata=metadata,
    )


def _record_generic_evidence(
    db: Session,
    *,
    organization_id: UUID,
    field_name: str,
    source_type: str,
    source_url: str | None,
    excerpt: str,
    confidence: float,
    metadata: dict[str, Any],
    relationship_entity_id: UUID | None = None,
    deal_id: UUID | None = None,
    interaction_id: UUID | None = None,
    action_item_id: UUID | None = None,
    document_id: UUID | None = None,
    connector_item_id: UUID | None = None,
) -> None:
    db.add(
        RelationshipEvidence(
            organization_id=organization_id,
            relationship_entity_id=relationship_entity_id,
            deal_id=deal_id,
            interaction_id=interaction_id,
            action_item_id=action_item_id,
            document_id=document_id,
            connector_item_id=connector_item_id,
            field_name=field_name,
            source_type=source_type,
            source_url=source_url,
            excerpt=excerpt[:1200],
            confidence=confidence,
            metadata_json=metadata,
        )
    )


def _latest_document_text(db: Session, document: Document) -> str:
    content = db.scalar(
        select(DerivedDocumentContent)
        .where(
            DerivedDocumentContent.document_id == document.id,
            DerivedDocumentContent.kind.in_(["cleaned", "extracted"]),
        )
        .order_by(DerivedDocumentContent.created_at.desc())
        .limit(1)
    )
    return content.text if content else ""


def _source_type(document: Document) -> str:
    metadata = document.custom_metadata or {}
    raw = str(metadata.get("source") or metadata.get("source_type") or "").lower()
    if "granola" in raw or "granola" in str(document.source_url or "").lower():
        return "granola"
    if raw == "telegram" or str(document.source_url or "").startswith("telegram:"):
        return "telegram"
    if raw:
        return raw[:80]
    return "document"


def _dedupe_entities(signals: list[EntitySignal]) -> list[EntitySignal]:
    best: dict[tuple[str, str], EntitySignal] = {}
    for signal in signals:
        key = (_normalize(signal.name), signal.entity_type)
        if key not in best or signal.confidence > best[key].confidence:
            best[key] = signal
    return sorted(best.values(), key=lambda item: item.confidence, reverse=True)[:60]


def _dedupe_actions(signals: list[ActionSignal]) -> list[ActionSignal]:
    best: dict[str, ActionSignal] = {}
    for signal in signals:
        key = _normalize(signal.title)
        if key and (key not in best or signal.confidence > best[key].confidence):
            best[key] = signal
    return list(best.values())[:40]


def _split_names(value: str) -> list[str]:
    pieces = re.split(r",|;|\s+\|\s+|\s+ and \s+| & ", value)
    names = []
    for piece in pieces:
        cleaned = _clean_name(re.sub(r"\([^)]*\)", "", piece))
        if cleaned:
            names.append(cleaned)
    return names


def _classify_label_value(label: str, value: str, context: str) -> tuple[str, tuple[str, ...]]:
    if label in {"investor", "fund"} or _looks_like_investor(value, context):
        return "investor", ("investor",)
    if label in {"founder", "management", "attendee", "attendees", "participant", "participants", "contact", "contacts"}:
        if _looks_like_company(value):
            return "company", ("mentioned",)
        return "person", _person_roles(context)
    if label in {"client", "company"}:
        return "company", ("client" if label == "client" else "prospective_client",)
    return "company", ("mentioned",)


def _looks_like_investor(value: str, context: str) -> bool:
    lowered = f"{value} {context}".lower()
    return any(hint in lowered for hint in INVESTOR_HINTS)


def _looks_like_company(value: str) -> bool:
    lowered = value.lower()
    return any(hint in lowered for hint in INVESTOR_HINTS | {"limited", "ltd", "inc", "corp", "group", "technologies"})


def _person_roles(context: str) -> tuple[str, ...]:
    lowered = context.lower()
    if "founder" in lowered:
        return ("founder", "contact")
    if "ceo" in lowered:
        return ("ceo", "contact")
    if "cfo" in lowered:
        return ("cfo", "contact")
    return ("contact",)


def _priority(value: str) -> str:
    lowered = value.lower()
    if any(word in lowered for word in ("urgent", "asap", "today", "tomorrow")):
        return "high"
    if any(word in lowered for word in ("low", "later", "someday")):
        return "low"
    return "medium"


def _first_amount(text: str) -> tuple[Decimal | None, str | None]:
    for match in AMOUNT_RE.finditer(text):
        context = _context(text, match.start()).lower()
        if not any(word in context for word in ("raise", "round", "deal", "valuation", "revenue", "ebitda", "investment", "ticket")):
            continue
        amount = Decimal(match.group("amount"))
        unit = (match.group("unit") or "").lower()
        if unit in {"m", "mn", "million"}:
            amount *= Decimal("1000000")
        elif unit in {"bn", "billion"}:
            amount *= Decimal("1000000000")
        elif unit in {"cr", "crore"}:
            amount *= Decimal("10000000")
        currency = _normalize_currency(match.group("currency"))
        return amount, currency
    return None, None


def _normalize_currency(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.upper().replace(".", "")
    if cleaned in {"$", "US$"}:
        return "USD"
    if cleaned in {"RS", "₹"}:
        return "INR"
    return cleaned


def _stage_from_text(lowered: str) -> str:
    if "closed" in lowered or "signed" in lowered:
        return "closed"
    if "term sheet" in lowered or "loi" in lowered:
        return "term_sheet"
    if "diligence" in lowered or "data room" in lowered:
        return "diligence"
    if "pitch" in lowered or "intro" in lowered:
        return "outreach"
    return "identified"


def _primary_entity(entity_by_key: dict[tuple[str, str], RelationshipEntity]) -> RelationshipEntity | None:
    companies = [entity for (_name, entity_type), entity in entity_by_key.items() if entity_type == "company"]
    if companies:
        return companies[0]
    investors = [entity for (_name, entity_type), entity in entity_by_key.items() if entity_type == "investor"]
    if investors:
        return investors[0]
    return next(iter(entity_by_key.values()), None)


def _deal_role_for_entity(entity: RelationshipEntity) -> str:
    if entity.entity_type == "investor":
        return "investor"
    if entity.entity_type == "person":
        return "contact"
    return "participant"


def _refresh_last_interaction(entity: RelationshipEntity, occurred_at: datetime | None) -> None:
    if occurred_at and (not entity.last_interaction_at or occurred_at > entity.last_interaction_at):
        entity.last_interaction_at = occurred_at


def _parse_first_date(text: str) -> datetime | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    value = match.group(1)
    for fmt in ("%Y-%m-%d", "%d %B %Y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _summary_from_lines(lines: list[str], fallback: str) -> str:
    body = " ".join(lines[:5]).strip()
    return (body or fallback or "Relationship interaction")[:900]


def _summary_from_text(text: str) -> str:
    return " ".join(text.split())[:900]


def _signal_summary(signal: EntitySignal) -> str:
    roles = ", ".join(signal.roles)
    return f"AI-detected {signal.entity_type} relationship signal" + (f" ({roles})." if roles else ".")


def _append_source(metadata: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    sources = [item for item in metadata.get("sources", []) if isinstance(item, dict)]
    source_key = str(source.get("document_id") or source.get("connector_item_id") or source.get("source_url") or "")
    if source_key and any(str(item.get("document_id") or item.get("connector_item_id") or item.get("source_url") or "") == source_key for item in sources):
        return metadata
    return {**metadata, "sources": [*sources[-19:], source]}


def _uuid_from_metadata(metadata: dict[str, Any], key: str) -> UUID | None:
    value = metadata.get(key)
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _clean_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _clean_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip(" -:\t\n\r"))
    cleaned = re.sub(r"^(the|a|an)\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned[:260]


def _clean_action(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip(" -:\t\n\r."))[:300]


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _is_noise_name(value: str) -> bool:
    lowered = value.lower()
    if len(value) < 3:
        return True
    return lowered in {
        "meeting",
        "minutes",
        "notes",
        "action",
        "follow up",
        "next steps",
        "team",
        "investor",
        "client",
    }


def _context(text: str, index: int, window: int = 360) -> str:
    start = max(0, index - window // 2)
    end = min(len(text), index + window // 2)
    return " ".join(text[start:end].split())[:700]
