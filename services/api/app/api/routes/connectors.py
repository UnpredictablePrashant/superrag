from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability, request_meta, require_organization
from app.core.permissions import require_capability
from app.core.security import encrypt_secret, mask_secret
from app.db.session import get_db
from app.models.entities import ConnectorConnection, ConnectorItem, ConnectorRun, KnowledgeBase
from app.schemas.api import (
    ConnectorConnectionCreateIn,
    ConnectorConnectionOut,
    ConnectorConnectionPatchIn,
    ConnectorItemOut,
    ConnectorRunOut,
    ConnectorSyncIn,
    DocumentOut,
    LiveResultSaveIn,
)
from app.services.audit import write_audit_log
from app.services.connectors import (
    connector_capability_metadata,
    get_connector_adapter,
    normalize_connector_config,
    save_live_result_as_document,
)
from app.workers.tasks import process_connector_sync_task

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("", response_model=list[ConnectorConnectionOut])
def list_connectors(
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = list(
        db.scalars(
            select(ConnectorConnection)
            .where(
                ConnectorConnection.organization_id == ctx.organization_id,
                ConnectorConnection.deleted_at.is_(None),
            )
            .order_by(ConnectorConnection.created_at.desc())
        )
    )
    visible = [
        connection
        for connection in rows
        if connection.scope == "organization" or connection.user_id == ctx.user.id
    ]
    return [_connection_out(db, connection) for connection in visible]


@router.post("", response_model=ConnectorConnectionOut)
def create_connector(
    payload: ConnectorConnectionCreateIn,
    request: Request,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> dict:
    base_url, config, secret = normalize_connector_config(
        kind=payload.kind,
        base_url=payload.base_url,
        config=payload.config,
        secret=payload.secret,
    )
    _require_scope_management(ctx, payload.scope, owner_user_id=ctx.user.id)
    duplicate = db.scalar(
        select(ConnectorConnection).where(
            ConnectorConnection.organization_id == ctx.organization_id,
            ConnectorConnection.name == payload.name,
            ConnectorConnection.scope == payload.scope,
            ConnectorConnection.user_id == (ctx.user.id if payload.scope == "user" else None),
            ConnectorConnection.deleted_at.is_(None),
        )
    )
    if duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A connector with this name already exists.")
    connection = ConnectorConnection(
        organization_id=ctx.organization_id,
        user_id=ctx.user.id if payload.scope == "user" else None,
        scope=payload.scope,
        kind=payload.kind,
        name=payload.name,
        encrypted_secret=encrypt_secret(secret) if secret else None,
        masked_secret=mask_secret(secret) if secret else None,
        base_url=base_url,
        is_enabled=payload.is_enabled,
        config=config,
    )
    db.add(connection)
    db.flush()
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="connector.created",
        resource_type="connector_connection",
        resource_id=str(connection.id),
        metadata={"kind": payload.kind, "scope": payload.scope},
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    db.refresh(connection)
    return _connection_out(db, connection)


@router.patch("/{connection_id}", response_model=ConnectorConnectionOut)
def patch_connector(
    connection_id: UUID,
    payload: ConnectorConnectionPatchIn,
    request: Request,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> dict:
    connection = _get_connection(db, ctx, connection_id, manage=True)
    base_url, config, extracted_secret = normalize_connector_config(
        kind=connection.kind,
        base_url=payload.base_url if payload.base_url is not None else connection.base_url,
        config=payload.config if payload.config is not None else connection.config,
        secret=payload.secret,
    )
    if payload.name is not None:
        connection.name = payload.name
    if extracted_secret is not None:
        connection.encrypted_secret = encrypt_secret(extracted_secret)
        connection.masked_secret = mask_secret(extracted_secret)
        connection.status = "rotated"
    if payload.base_url is not None or base_url != connection.base_url:
        connection.base_url = base_url
    if payload.is_enabled is not None:
        connection.is_enabled = payload.is_enabled
    if payload.config is not None:
        connection.config = config
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="connector.updated",
        resource_type="connector_connection",
        resource_id=str(connection.id),
        metadata={"secret_rotated": payload.secret is not None},
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    db.refresh(connection)
    return _connection_out(db, connection)


@router.delete("/{connection_id}")
def delete_connector(
    connection_id: UUID,
    request: Request,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> dict:
    connection = _get_connection(db, ctx, connection_id, manage=True)
    connection.deleted_at = datetime.now(UTC)
    connection.is_enabled = False
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="connector.deleted",
        resource_type="connector_connection",
        resource_id=str(connection.id),
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    return {"message": "Connector deleted."}


@router.post("/{connection_id}/test")
def test_connector(
    connection_id: UUID,
    request: Request,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> dict:
    connection = _get_connection(db, ctx, connection_id, manage=True)
    try:
        result = get_connector_adapter(connection).test_connection()
        connection.status = result.get("status", "ok")
        if connection.kind == "mcp" and result.get("status") == "ok":
            connection.config = {
                **(connection.config or {}),
                "discovered_tools": result.get("tools", []),
                "discovered_resources": result.get("resources", []),
                "last_discovered_at": datetime.now(UTC).isoformat(),
            }
    except Exception as exc:
        connection.status = "error"
        result = {"status": "error", "message": str(exc)[:500]}
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="connector.tested",
        resource_type="connector_connection",
        resource_id=str(connection.id),
        metadata={"status": result.get("status")},
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    return result


def _connection_out(db: Session, connection: ConnectorConnection) -> dict:
    return {
        "id": connection.id,
        "kind": connection.kind,
        "scope": connection.scope,
        "user_id": connection.user_id,
        "name": connection.name,
        "masked_secret": connection.masked_secret,
        "base_url": connection.base_url,
        "status": connection.status,
        "is_enabled": connection.is_enabled,
        "config": connection.config,
        "last_synced_at": connection.last_synced_at,
        "created_at": connection.created_at,
        "updated_at": connection.updated_at,
        **connector_capability_metadata(db, connection),
    }


@router.post("/{connection_id}/sync", response_model=ConnectorRunOut)
def sync_connector(
    connection_id: UUID,
    payload: ConnectorSyncIn,
    request: Request,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> ConnectorRun:
    connection = _get_connection(db, ctx, connection_id, manage=False)
    _require_sync_permission(ctx, connection)
    kb = db.get(KnowledgeBase, payload.knowledge_base_id)
    if not kb or kb.organization_id != ctx.organization_id or kb.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")
    options = {
        **payload.options,
        "knowledge_base_id": str(payload.knowledge_base_id),
        "cleanup_profile_id": str(payload.cleanup_profile_id) if payload.cleanup_profile_id else None,
        "chunking_profile_id": str(payload.chunking_profile_id) if payload.chunking_profile_id else None,
        "embedding_profile_id": str(payload.embedding_profile_id) if payload.embedding_profile_id else None,
        "retrieval_index_config": payload.retrieval_index_config,
        "share_with_organization": payload.share_with_organization,
    }
    run = ConnectorRun(
        organization_id=ctx.organization_id,
        connector_connection_id=connection.id,
        requested_by_user_id=ctx.user.id,
        status="queued",
        options=options,
    )
    db.add(run)
    db.flush()
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="connector.sync_queued",
        resource_type="connector_connection",
        resource_id=str(connection.id),
        metadata={"connector_run_id": str(run.id), "knowledge_base_id": str(payload.knowledge_base_id)},
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    process_connector_sync_task.delay(str(connection.id), str(ctx.user.id), options, str(run.id))
    db.refresh(run)
    return run


@router.get("/{connection_id}/runs", response_model=list[ConnectorRunOut])
def list_connector_runs(
    connection_id: UUID,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> list[ConnectorRun]:
    connection = _get_connection(db, ctx, connection_id, manage=False)
    return list(
        db.scalars(
            select(ConnectorRun)
            .where(ConnectorRun.connector_connection_id == connection.id)
            .order_by(ConnectorRun.created_at.desc())
            .limit(50)
        )
    )


@router.get("/{connection_id}/items", response_model=list[ConnectorItemOut])
def list_connector_items(
    connection_id: UUID,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> list[ConnectorItem]:
    connection = _get_connection(db, ctx, connection_id, manage=False)
    return list(
        db.scalars(
            select(ConnectorItem)
            .where(ConnectorItem.connector_connection_id == connection.id)
            .order_by(ConnectorItem.updated_at.desc())
            .limit(100)
        )
    )


@router.post("/live-results", response_model=DocumentOut)
def save_live_result(
    payload: LiveResultSaveIn,
    request: Request,
    ctx: AuthContext = Depends(capability("upload_documents")),
    db: Session = Depends(get_db),
):
    kb = db.get(KnowledgeBase, payload.knowledge_base_id)
    if not kb or kb.organization_id != ctx.organization_id or kb.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")
    document = save_live_result_as_document(
        db,
        organization_id=ctx.organization_id,
        user_id=ctx.user.id,
        knowledge_base_id=payload.knowledge_base_id,
        title=payload.title,
        content=payload.content,
        source_url=payload.source_url,
        source_type=payload.source_type,
        confidentiality=payload.confidentiality,
        tags=payload.tags,
        share_with_organization=payload.share_with_organization,
        custom_metadata=payload.custom_metadata,
    )
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="connector.live_result_saved",
        resource_type="document",
        resource_id=str(document.id),
        metadata={"source_url": payload.source_url, "source_type": payload.source_type},
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    db.refresh(document)
    return document


def _get_connection(
    db: Session,
    ctx: AuthContext,
    connection_id: UUID,
    *,
    manage: bool,
) -> ConnectorConnection:
    connection = db.get(ConnectorConnection, connection_id)
    if not connection or connection.organization_id != ctx.organization_id or connection.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Connector not found.")
    if connection.scope == "user" and connection.user_id != ctx.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Connector not found.")
    if manage:
        _require_scope_management(ctx, connection.scope, owner_user_id=connection.user_id)
    return connection


def _require_scope_management(ctx: AuthContext, scope: str, owner_user_id: UUID | None) -> None:
    if scope == "organization":
        require_capability(ctx.role or "", "manage_org_connectors")
        return
    require_capability(ctx.role or "", "manage_own_connectors")
    if owner_user_id and owner_user_id != ctx.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Connector not found.")


def _require_sync_permission(ctx: AuthContext, connection: ConnectorConnection) -> None:
    if connection.scope == "organization":
        require_capability(ctx.role or "", "run_ingestion")
        return
    if connection.user_id != ctx.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Connector not found.")
    require_capability(ctx.role or "", "manage_own_connectors")
