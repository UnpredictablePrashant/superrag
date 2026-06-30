from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_organization
from app.db.session import get_db
from app.models.entities import (
    ConnectorConnection,
    ConnectorRun,
    Document,
    DocumentStatus,
    KnowledgeBase,
    ModelProfile,
    Organization,
    ProviderConnection,
    ProviderKind,
    PipelineRun,
    PipelineStage,
    ProfileKind,
    TelegramMessageLog,
)
from app.schemas.api import OrganizationOut, WorkspaceSummaryOut
from app.services.connectors import connector_capability_metadata

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/summary", response_model=WorkspaceSummaryOut)
def workspace_summary(
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> WorkspaceSummaryOut:
    organization = db.get(Organization, ctx.organization_id)
    document_count = _count(
        db,
        select(func.count(Document.id)).where(
            Document.organization_id == ctx.organization_id,
            Document.deleted_at.is_(None),
        ),
    )
    indexed_document_count = _count(
        db,
        select(func.count(Document.id)).where(
            Document.organization_id == ctx.organization_id,
            Document.deleted_at.is_(None),
            Document.processing_status.in_(
                [DocumentStatus.COMPLETED, DocumentStatus.COMPLETED_WITH_WARNINGS]
            ),
        ),
    )
    knowledge_base_count = _count(
        db,
        select(func.count(KnowledgeBase.id)).where(
            KnowledgeBase.organization_id == ctx.organization_id,
            KnowledgeBase.deleted_at.is_(None),
        ),
    )
    connectors = list(
        db.scalars(
            select(ConnectorConnection).where(
                ConnectorConnection.organization_id == ctx.organization_id,
                ConnectorConnection.deleted_at.is_(None),
            )
        )
    )
    visible_connectors = [
        connector
        for connector in connectors
        if connector.scope == "organization" or connector.user_id == ctx.user.id
    ]
    active_connectors = [connector for connector in visible_connectors if connector.is_enabled]
    connector_metadata = [connector_capability_metadata(db, connector) for connector in active_connectors]
    failed_sync_count = _count(
        db,
        select(func.count(ConnectorRun.id)).where(
            ConnectorRun.organization_id == ctx.organization_id,
            ConnectorRun.status == "failed",
        ),
    )
    failed_connector_count = len([connector for connector in visible_connectors if connector.status == "error"])
    failed_pipeline_count = _count(
        db,
        select(func.count(PipelineRun.id)).where(
            PipelineRun.organization_id == ctx.organization_id,
            PipelineRun.current_stage == PipelineStage.FAILED,
        ),
    )
    failed_telegram_count = _count(
        db,
        select(func.count(TelegramMessageLog.id)).where(
            TelegramMessageLog.organization_id == ctx.organization_id,
            TelegramMessageLog.status == "failed",
        ),
    )
    review_document_count = _count(
        db,
        select(func.count(Document.id)).where(
            Document.organization_id == ctx.organization_id,
            Document.deleted_at.is_(None),
            Document.processing_status.in_([DocumentStatus.AWAITING_REVIEW, DocumentStatus.FAILED]),
        ),
    )
    default_kb = db.scalar(
        select(KnowledgeBase)
        .where(KnowledgeBase.organization_id == ctx.organization_id, KnowledgeBase.deleted_at.is_(None))
        .order_by(KnowledgeBase.updated_at.desc())
        .limit(1)
    )
    default_chat_model = db.scalar(
        select(ModelProfile)
        .where(
            ModelProfile.organization_id == ctx.organization_id,
            ModelProfile.kind == ProfileKind.CHAT,
            ModelProfile.deleted_at.is_(None),
            ~(
                (ModelProfile.provider_connection_id.is_(None))
                & (ModelProfile.model_name == "deterministic-local-384")
            ),
        )
        .order_by(ModelProfile.is_default.desc(), ModelProfile.created_at)
        .limit(1)
    )
    has_openai_web_search = db.scalar(
        select(func.count(ProviderConnection.id)).where(
            ProviderConnection.organization_id == ctx.organization_id,
            ProviderConnection.provider == ProviderKind.OPENAI,
            ProviderConnection.deleted_at.is_(None),
            ProviderConnection.is_enabled.is_(True),
            ProviderConnection.encrypted_api_key.is_not(None),
        )
    )
    available_modes = _available_answer_modes(indexed_document_count, connector_metadata, bool(has_openai_web_search))
    return WorkspaceSummaryOut(
        organization=OrganizationOut.model_validate(organization) if organization else None,
        document_count=document_count,
        indexed_document_count=indexed_document_count,
        knowledge_base_count=knowledge_base_count,
        active_source_count=len(active_connectors),
        failed_sync_count=failed_sync_count + failed_connector_count,
        review_item_count=review_document_count
        + failed_pipeline_count
        + failed_sync_count
        + failed_connector_count
        + failed_telegram_count,
        available_answer_modes=available_modes,
        default_knowledge_base=_knowledge_base_summary(default_kb),
        default_chat_model=_chat_model_summary(default_chat_model),
        source_health={
            "active": len(active_connectors),
            "error": failed_connector_count,
            "sync_failed": failed_sync_count,
            "telegram_failed": failed_telegram_count,
            "indexed_items": sum(int(meta["indexed_item_count"]) for meta in connector_metadata),
        },
    )


def _available_answer_modes(
    indexed_document_count: int,
    connector_metadata: list[dict[str, Any]],
    has_openai_web_search: bool = False,
) -> list[str]:
    modes: list[str] = []
    if indexed_document_count:
        modes.append("company_data")
    has_live_web = has_openai_web_search or any(meta.get("web_search_supported") for meta in connector_metadata)
    has_mcp = any(meta.get("live_tools_supported") for meta in connector_metadata)
    if has_live_web:
        modes.append("live_web")
    if has_mcp:
        modes.append("mcp_tools")
    if indexed_document_count and (has_live_web or has_mcp):
        modes.append("blended")
    return modes or ["company_data"]


def _knowledge_base_summary(kb: KnowledgeBase | None) -> dict[str, Any] | None:
    if not kb:
        return None
    return {"id": str(kb.id), "name": kb.name, "confidentiality": kb.confidentiality.value}


def _chat_model_summary(profile: ModelProfile | None) -> dict[str, Any] | None:
    if not profile:
        return {"id": None, "name": "No chat model configured", "provider": "LLM", "model_name": "not configured"}
    return {
        "id": str(profile.id),
        "name": profile.name,
        "provider": str(profile.config.get("provider") or "Local"),
        "model_name": profile.model_name,
    }


def _count(db: Session, statement) -> int:
    return int(db.scalar(statement) or 0)
