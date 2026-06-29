from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability
from app.db.session import get_db
from app.schemas.api import RetrievalSearchIn
from app.services.retrieval import retrieve

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.post("/search")
def search(
    payload: RetrievalSearchIn,
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> dict:
    candidates, event = retrieve(
        db,
        organization_id=ctx.organization_id,
        user_id=ctx.user.id,
        role=ctx.role or "",
        query=payload.query,
        knowledge_base_ids=[str(value) for value in payload.knowledge_base_ids],
        filters=payload.filters,
        debug=False,
    )
    db.commit()
    return {
        "results": [
            {
                "chunk_id": candidate.chunk_id,
                "document_id": candidate.document_id,
                "document_name": candidate.document_name,
                "score": candidate.score,
                "preview": candidate.text[:600],
                "metadata": candidate.metadata,
            }
            for candidate in candidates
        ],
        "retrieval_event_id": str(event.id),
    }


@router.post("/debug")
def debug_search(
    payload: RetrievalSearchIn,
    ctx: AuthContext = Depends(capability("view_audit_logs")),
    db: Session = Depends(get_db),
) -> dict:
    candidates, event = retrieve(
        db,
        organization_id=ctx.organization_id,
        user_id=ctx.user.id,
        role=ctx.role or "",
        query=payload.query,
        knowledge_base_ids=[str(value) for value in payload.knowledge_base_ids],
        filters=payload.filters,
        debug=True,
    )
    db.commit()
    return {
        "results": [
            {
                "chunk_id": candidate.chunk_id,
                "document_id": candidate.document_id,
                "document_name": candidate.document_name,
                "score": candidate.score,
                "preview": candidate.text[:600],
                "metadata": candidate.metadata,
            }
            for candidate in candidates
        ],
        "debug": {
            "original_query": event.original_query,
            "rewritten_query": event.rewritten_query,
            "applied_filters": event.applied_filters,
            "vector_candidates": event.vector_candidates,
            "keyword_candidates": event.keyword_candidates,
            "rrf_ranking": event.rrf_ranking,
            "reranker_scores": event.reranker_scores,
            "final_context_chunks": event.final_context_chunks,
            "token_usage": event.token_usage,
            "latency_ms_by_stage": event.latency_ms_by_stage,
        },
        "retrieval_event_id": str(event.id),
    }
