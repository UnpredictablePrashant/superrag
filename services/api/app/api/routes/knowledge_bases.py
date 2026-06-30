from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability, request_meta, require_organization
from app.db.session import get_db
from app.models.entities import Category, KnowledgeBase
from app.schemas.api import (
    CategoryCreateIn,
    CategoryOut,
    KnowledgeBaseCreateIn,
    KnowledgeBaseOut,
    KnowledgeBasePatchIn,
)
from app.services.audit import write_audit_log
from app.services.profiles import default_pipeline_profile_ids

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


@router.get("", response_model=list[KnowledgeBaseOut])
def list_knowledge_bases(
    ctx: AuthContext = Depends(require_organization), db: Session = Depends(get_db)
) -> list[KnowledgeBase]:
    return list(
        db.scalars(
            select(KnowledgeBase)
            .where(KnowledgeBase.organization_id == ctx.organization_id, KnowledgeBase.deleted_at.is_(None))
            .order_by(KnowledgeBase.name)
        )
    )


@router.post("", response_model=KnowledgeBaseOut)
def create_knowledge_base(
    payload: KnowledgeBaseCreateIn,
    request: Request,
    ctx: AuthContext = Depends(capability("create_knowledge_bases")),
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    default_profiles = default_pipeline_profile_ids(db, ctx.organization_id)
    kb = KnowledgeBase(
        organization_id=ctx.organization_id,
        name=payload.name,
        description=payload.description,
        owner_user_id=ctx.user.id,
        default_cleanup_profile_id=default_profiles.get("cleanup_profile_id"),
        default_chunking_profile_id=default_profiles.get("chunking_profile_id"),
        default_embedding_profile_id=default_profiles.get("embedding_profile_id"),
        tags=payload.tags,
        confidentiality=payload.confidentiality,
        default_retrieval_config={
            "retrieval_algorithm": "hybrid_rrf",
            "vector_candidate_count": 40,
            "keyword_candidate_count": 40,
            "rerank_candidates": 20,
            "rrf_constant": 60,
            "max_chunks": 8,
            "similarity_threshold": 0.1,
            "indexing_strategy": "full_replace_chunks_and_vectors",
        },
    )
    db.add(kb)
    db.flush()
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="knowledge_base.created",
        resource_type="knowledge_base",
        resource_id=str(kb.id),
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    db.refresh(kb)
    return kb


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseOut)
def get_knowledge_base(
    knowledge_base_id: UUID,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    kb = _get_kb(db, ctx.organization_id, knowledge_base_id)
    return kb


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseOut)
def patch_knowledge_base(
    knowledge_base_id: UUID,
    payload: KnowledgeBasePatchIn,
    ctx: AuthContext = Depends(capability("create_knowledge_bases")),
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    kb = _get_kb(db, ctx.organization_id, knowledge_base_id)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(kb, key, value)
    db.commit()
    db.refresh(kb)
    return kb


@router.delete("/{knowledge_base_id}")
def delete_knowledge_base(
    knowledge_base_id: UUID,
    ctx: AuthContext = Depends(capability("create_knowledge_bases")),
    db: Session = Depends(get_db),
) -> dict:
    kb = _get_kb(db, ctx.organization_id, knowledge_base_id)
    kb.deleted_at = datetime.now(UTC)
    db.commit()
    return {"message": "Knowledge base deleted."}


@router.get("/{knowledge_base_id}/categories", response_model=list[CategoryOut])
def list_categories(
    knowledge_base_id: UUID,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> list[Category]:
    _get_kb(db, ctx.organization_id, knowledge_base_id)
    return list(
        db.scalars(
            select(Category)
            .where(
                Category.organization_id == ctx.organization_id,
                Category.knowledge_base_id == knowledge_base_id,
                Category.deleted_at.is_(None),
            )
            .order_by(Category.path)
        )
    )


@router.post("/{knowledge_base_id}/categories", response_model=CategoryOut)
def create_category(
    knowledge_base_id: UUID,
    payload: CategoryCreateIn,
    ctx: AuthContext = Depends(capability("create_knowledge_bases")),
    db: Session = Depends(get_db),
) -> Category:
    _get_kb(db, ctx.organization_id, knowledge_base_id)
    parent = None
    if payload.parent_id:
        parent = db.get(Category, payload.parent_id)
        if not parent or parent.organization_id != ctx.organization_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Parent category not found.")
    path = f"{parent.path}/{payload.name}" if parent else payload.name
    category = Category(
        organization_id=ctx.organization_id,
        knowledge_base_id=knowledge_base_id,
        parent_id=payload.parent_id,
        name=payload.name,
        path=path,
        access_policy=payload.access_policy,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def _get_kb(db: Session, organization_id: UUID, knowledge_base_id: UUID) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, knowledge_base_id)
    if not kb or kb.organization_id != organization_id or kb.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")
    return kb
