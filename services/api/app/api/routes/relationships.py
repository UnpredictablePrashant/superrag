from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability, request_meta, require_organization
from app.db.session import get_db
from app.models.entities import (
    ActionItem,
    Deal,
    DealParticipant,
    Interaction,
    InteractionParticipant,
    RelationshipEntity,
    RelationshipEvidence,
    RelationshipRole,
)
from app.schemas.api import (
    ActionItemCreateIn,
    ActionItemOut,
    ActionItemPatchIn,
    DealOut,
    InteractionOut,
    RelationshipEntityDetailOut,
    RelationshipEntityOut,
    RelationshipEvidenceOut,
    RelationshipRescanIn,
    RelationshipRescanOut,
    RelationshipRoleOut,
    RelationshipSummaryOut,
)
from app.services.audit import write_audit_log
from app.services.relationship_intelligence import rescan_relationship_intelligence

router = APIRouter(prefix="/relationships", tags=["relationships"])


@router.get("/summary", response_model=RelationshipSummaryOut)
def relationship_summary(
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> RelationshipSummaryOut:
    org_id = ctx.organization_id
    entity_count = _count(db, RelationshipEntity, org_id)
    client_count = _role_count(db, org_id, "client")
    investor_count = _entity_type_count(db, org_id, "investor")
    contact_count = _entity_type_count(db, org_id, "person")
    open_action_count = int(
        db.scalar(
            select(func.count(ActionItem.id)).where(
                ActionItem.organization_id == org_id,
                ActionItem.status == "open",
            )
        )
        or 0
    )
    overdue_action_count = int(
        db.scalar(
            select(func.count(ActionItem.id)).where(
                ActionItem.organization_id == org_id,
                ActionItem.status == "open",
                ActionItem.due_at.is_not(None),
                ActionItem.due_at < datetime.now(UTC),
            )
        )
        or 0
    )
    recent_interactions = [
        _interaction_out(db, row)
        for row in db.scalars(
            select(Interaction)
            .where(Interaction.organization_id == org_id)
            .order_by(Interaction.occurred_at.desc().nullslast(), Interaction.created_at.desc())
            .limit(5)
        )
    ]
    upcoming_actions = [
        _action_out(db, row)
        for row in db.scalars(
            select(ActionItem)
            .where(ActionItem.organization_id == org_id, ActionItem.status == "open")
            .order_by(ActionItem.due_at.asc().nullslast(), ActionItem.created_at.desc())
            .limit(6)
        )
    ]
    review_count = int(
        db.scalar(
            select(func.count(RelationshipEntity.id)).where(
                RelationshipEntity.organization_id == org_id,
                RelationshipEntity.deleted_at.is_(None),
                RelationshipEntity.status == "suggested",
            )
        )
        or 0
    )
    return RelationshipSummaryOut(
        entity_count=entity_count,
        client_count=client_count,
        investor_count=investor_count,
        contact_count=contact_count,
        open_action_count=open_action_count,
        overdue_action_count=overdue_action_count,
        deal_count=_count(db, Deal, org_id),
        interaction_count=_count(db, Interaction, org_id),
        review_count=review_count,
        recent_interactions=recent_interactions,
        upcoming_actions=upcoming_actions,
    )


@router.get("/entities", response_model=list[RelationshipEntityOut])
def list_relationship_entities(
    search: str | None = None,
    entity_type: str | None = None,
    role: str | None = None,
    status_filter: str | None = None,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> list[RelationshipEntityOut]:
    query = select(RelationshipEntity).where(
        RelationshipEntity.organization_id == ctx.organization_id,
        RelationshipEntity.deleted_at.is_(None),
    )
    if search:
        query = query.where(RelationshipEntity.name.ilike(f"%{search}%"))
    if entity_type:
        query = query.where(RelationshipEntity.entity_type == entity_type)
    if status_filter:
        query = query.where(RelationshipEntity.status == status_filter)
    if role:
        query = query.join(RelationshipRole, RelationshipRole.relationship_entity_id == RelationshipEntity.id).where(
            RelationshipRole.role_name == role
        )
    rows = db.scalars(
        query.order_by(RelationshipEntity.last_interaction_at.desc().nullslast(), RelationshipEntity.updated_at.desc()).limit(200)
    )
    return [_entity_out(db, row) for row in rows]


@router.get("/entities/{entity_id}", response_model=RelationshipEntityDetailOut)
def get_relationship_entity(
    entity_id: UUID,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> RelationshipEntityDetailOut:
    entity = _get_entity(db, ctx.organization_id, entity_id)
    base = _entity_out(db, entity).model_dump()
    roles = list(
        db.scalars(
            select(RelationshipRole)
            .where(RelationshipRole.relationship_entity_id == entity.id)
            .order_by(RelationshipRole.created_at)
        )
    )
    evidence = list(
        db.scalars(
            select(RelationshipEvidence)
            .where(RelationshipEvidence.relationship_entity_id == entity.id)
            .order_by(RelationshipEvidence.created_at.desc())
            .limit(50)
        )
    )
    interaction_ids = list(
        db.scalars(
            select(InteractionParticipant.interaction_id)
            .where(InteractionParticipant.relationship_entity_id == entity.id)
            .order_by(InteractionParticipant.created_at.desc())
            .limit(50)
        )
    )
    interactions = [
        _interaction_out(db, row)
        for row in db.scalars(
            select(Interaction)
            .where(Interaction.id.in_(interaction_ids) if interaction_ids else false())
            .order_by(Interaction.occurred_at.desc().nullslast(), Interaction.created_at.desc())
        )
    ]
    deal_ids = list(
        db.scalars(
            select(DealParticipant.deal_id)
            .where(DealParticipant.relationship_entity_id == entity.id)
            .order_by(DealParticipant.created_at.desc())
            .limit(50)
        )
    )
    deals = [
        _deal_out(db, row)
        for row in db.scalars(
            select(Deal)
            .where(or_(Deal.id.in_(deal_ids) if deal_ids else false(), Deal.company_entity_id == entity.id))
            .where(Deal.deleted_at.is_(None))
            .order_by(Deal.updated_at.desc())
        )
    ]
    actions = [
        _action_out(db, row)
        for row in db.scalars(
            select(ActionItem)
            .where(ActionItem.relationship_entity_id == entity.id)
            .order_by(ActionItem.status, ActionItem.due_at.asc().nullslast(), ActionItem.created_at.desc())
            .limit(50)
        )
    ]
    return RelationshipEntityDetailOut(
        **base,
        roles=[RelationshipRoleOut.model_validate(row) for row in roles],
        evidence=[RelationshipEvidenceOut.model_validate(row) for row in evidence],
        interactions=interactions,
        deals=deals,
        action_items=actions,
    )


@router.get("/interactions", response_model=list[InteractionOut])
def list_interactions(
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> list[InteractionOut]:
    return [
        _interaction_out(db, row)
        for row in db.scalars(
            select(Interaction)
            .where(Interaction.organization_id == ctx.organization_id)
            .order_by(Interaction.occurred_at.desc().nullslast(), Interaction.created_at.desc())
            .limit(100)
        )
    ]


@router.get("/deals", response_model=list[DealOut])
def list_deals(
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> list[DealOut]:
    return [
        _deal_out(db, row)
        for row in db.scalars(
            select(Deal)
            .where(Deal.organization_id == ctx.organization_id, Deal.deleted_at.is_(None))
            .order_by(Deal.updated_at.desc())
            .limit(100)
        )
    ]


@router.get("/action-items", response_model=list[ActionItemOut])
def list_action_items(
    status_filter: str | None = None,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> list[ActionItemOut]:
    query = select(ActionItem).where(ActionItem.organization_id == ctx.organization_id)
    if status_filter:
        query = query.where(ActionItem.status == status_filter)
    return [
        _action_out(db, row)
        for row in db.scalars(query.order_by(ActionItem.due_at.asc().nullslast(), ActionItem.created_at.desc()).limit(150))
    ]


@router.post("/action-items", response_model=ActionItemOut)
def create_action_item(
    payload: ActionItemCreateIn,
    request: Request,
    ctx: AuthContext = Depends(capability("upload_documents")),
    db: Session = Depends(get_db),
) -> ActionItemOut:
    _validate_related_records(db, ctx.organization_id, payload.relationship_entity_id, payload.deal_id, payload.interaction_id)
    action = ActionItem(
        organization_id=ctx.organization_id,
        title=payload.title,
        description=payload.description,
        relationship_entity_id=payload.relationship_entity_id,
        deal_id=payload.deal_id,
        interaction_id=payload.interaction_id,
        owner_user_id=payload.owner_user_id,
        due_at=payload.due_at,
        priority=payload.priority,
        status="open",
        source_type="manual",
        confidence=1,
        metadata_json={"created_from": "relationship_workspace"},
    )
    db.add(action)
    db.flush()
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="relationship.action_item_created",
        resource_type="action_item",
        resource_id=str(action.id),
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    db.refresh(action)
    return _action_out(db, action)


@router.patch("/action-items/{action_item_id}", response_model=ActionItemOut)
def patch_action_item(
    action_item_id: UUID,
    payload: ActionItemPatchIn,
    request: Request,
    ctx: AuthContext = Depends(capability("upload_documents")),
    db: Session = Depends(get_db),
) -> ActionItemOut:
    action = db.get(ActionItem, action_item_id)
    if not action or action.organization_id != ctx.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Action item not found.")
    for field in ("title", "description", "owner_user_id", "due_at", "priority", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(action, field, value)
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="relationship.action_item_updated",
        resource_type="action_item",
        resource_id=str(action.id),
        metadata={"status": action.status},
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    db.refresh(action)
    return _action_out(db, action)


@router.post("/rescan", response_model=RelationshipRescanOut)
def rescan_relationships(
    payload: RelationshipRescanIn,
    request: Request,
    ctx: AuthContext = Depends(capability("run_ingestion")),
    db: Session = Depends(get_db),
) -> RelationshipRescanOut:
    result = rescan_relationship_intelligence(
        db,
        organization_id=ctx.organization_id,
        document_ids=payload.document_ids or None,
    )
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="relationship.rescan",
        resource_type="relationship_intelligence",
        metadata={"document_count": len(payload.document_ids), **result},
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    return RelationshipRescanOut(**result)


def _count(db: Session, model, org_id: UUID) -> int:
    query = select(func.count(model.id)).where(model.organization_id == org_id)
    if hasattr(model, "deleted_at"):
        query = query.where(model.deleted_at.is_(None))
    return int(db.scalar(query) or 0)


def _entity_type_count(db: Session, org_id: UUID, entity_type: str) -> int:
    return int(
        db.scalar(
            select(func.count(RelationshipEntity.id)).where(
                RelationshipEntity.organization_id == org_id,
                RelationshipEntity.entity_type == entity_type,
                RelationshipEntity.deleted_at.is_(None),
            )
        )
        or 0
    )


def _role_count(db: Session, org_id: UUID, role_name: str) -> int:
    return int(
        db.scalar(
            select(func.count(RelationshipRole.id)).where(
                RelationshipRole.organization_id == org_id,
                RelationshipRole.role_name == role_name,
            )
        )
        or 0
    )


def _get_entity(db: Session, org_id: UUID, entity_id: UUID) -> RelationshipEntity:
    entity = db.get(RelationshipEntity, entity_id)
    if not entity or entity.organization_id != org_id or entity.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Relationship entity not found.")
    return entity


def _entity_out(db: Session, entity: RelationshipEntity) -> RelationshipEntityOut:
    role_names = list(
        db.scalars(
            select(RelationshipRole.role_name)
            .where(RelationshipRole.relationship_entity_id == entity.id)
            .order_by(RelationshipRole.role_name)
        )
    )
    evidence_count = int(
        db.scalar(
            select(func.count(RelationshipEvidence.id)).where(
                RelationshipEvidence.relationship_entity_id == entity.id
            )
        )
        or 0
    )
    open_action_count = int(
        db.scalar(
            select(func.count(ActionItem.id)).where(
                ActionItem.relationship_entity_id == entity.id,
                ActionItem.status == "open",
            )
        )
        or 0
    )
    return RelationshipEntityOut(
        **RelationshipEntityOut.model_validate(entity).model_dump(exclude={"role_names", "evidence_count", "open_action_count"}),
        role_names=role_names,
        evidence_count=evidence_count,
        open_action_count=open_action_count,
    )


def _interaction_out(db: Session, interaction: Interaction) -> InteractionOut:
    participants = [
        {"entity_id": str(entity.id), "name": entity.name, "entity_type": entity.entity_type, "role_name": role}
        for entity, role in db.execute(
            select(RelationshipEntity, InteractionParticipant.role_name)
            .join(InteractionParticipant, InteractionParticipant.relationship_entity_id == RelationshipEntity.id)
            .where(InteractionParticipant.interaction_id == interaction.id)
            .order_by(RelationshipEntity.name)
        )
    ]
    return InteractionOut(
        **InteractionOut.model_validate(interaction).model_dump(exclude={"participants"}),
        participants=participants,
    )


def _deal_out(db: Session, deal: Deal) -> DealOut:
    participants = [
        {"entity_id": str(entity.id), "name": entity.name, "entity_type": entity.entity_type, "role_name": role}
        for entity, role in db.execute(
            select(RelationshipEntity, DealParticipant.role_name)
            .join(DealParticipant, DealParticipant.relationship_entity_id == RelationshipEntity.id)
            .where(DealParticipant.deal_id == deal.id)
            .order_by(RelationshipEntity.name)
        )
    ]
    return DealOut(**DealOut.model_validate(deal).model_dump(exclude={"participants"}), participants=participants)


def _action_out(db: Session, action: ActionItem) -> ActionItemOut:
    entity_name = None
    if action.relationship_entity_id:
        entity = db.get(RelationshipEntity, action.relationship_entity_id)
        entity_name = entity.name if entity else None
    deal_name = None
    if action.deal_id:
        deal = db.get(Deal, action.deal_id)
        deal_name = deal.name if deal else None
    return ActionItemOut(
        **ActionItemOut.model_validate(action).model_dump(exclude={"entity_name", "deal_name"}),
        entity_name=entity_name,
        deal_name=deal_name,
    )


def _validate_related_records(
    db: Session,
    org_id: UUID,
    entity_id: UUID | None,
    deal_id: UUID | None,
    interaction_id: UUID | None,
) -> None:
    if entity_id:
        _get_entity(db, org_id, entity_id)
    if deal_id:
        deal = db.get(Deal, deal_id)
        if not deal or deal.organization_id != org_id or deal.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Deal not found.")
    if interaction_id:
        interaction = db.get(Interaction, interaction_id)
        if not interaction or interaction.organization_id != org_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Interaction not found.")
