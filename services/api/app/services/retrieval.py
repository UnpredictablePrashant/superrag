from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.models.entities import EmbeddingProfile, KnowledgeBase, ProviderConnection, RetrievalEvent
from app.services.embeddings import get_embedding_provider
from app.services.profiles import ensure_default_profiles


@dataclass
class Candidate:
    chunk_id: str
    document_id: str
    document_name: str
    text: str
    score: float
    source: str
    metadata: dict[str, Any]


def reciprocal_rank_fusion(
    vector_candidates: list[Candidate],
    keyword_candidates: list[Candidate],
    k: int = 60,
) -> list[Candidate]:
    scores: dict[str, float] = {}
    merged: dict[str, Candidate] = {}
    for ranking in (vector_candidates, keyword_candidates):
        for rank, candidate in enumerate(ranking, start=1):
            scores[candidate.chunk_id] = scores.get(candidate.chunk_id, 0.0) + 1 / (k + rank)
            if candidate.chunk_id not in merged or candidate.score > merged[candidate.chunk_id].score:
                merged[candidate.chunk_id] = candidate
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [
        Candidate(
            **{
                **merged[chunk_id].__dict__,
                "score": score,
                "source": "hybrid_rrf",
            }
        )
        for chunk_id, score in ordered
    ]


def rerank_lexical(query: str, candidates: list[Candidate], limit: int = 10) -> list[Candidate]:
    terms = {term.lower() for term in query.split() if len(term) > 2}
    reranked = []
    for candidate in candidates:
        body_terms = set(candidate.text.lower().split())
        overlap = len(terms & body_terms) / max(1, len(terms))
        reranked.append(
            Candidate(
                candidate.chunk_id,
                candidate.document_id,
                candidate.document_name,
                candidate.text,
                candidate.score + overlap,
                "local_reranker",
                {**candidate.metadata, "reranker_overlap": overlap},
            )
        )
    return sorted(reranked, key=lambda item: item.score, reverse=True)[:limit]


def retrieve(
    db: Session,
    *,
    organization_id: UUID,
    user_id: UUID,
    role: str,
    query: str,
    knowledge_base_ids: list[str] | None,
    filters: dict[str, Any] | None = None,
    debug: bool = False,
    chat_session_id: UUID | None = None,
) -> tuple[list[Candidate], RetrievalEvent]:
    filters = filters or {}
    started = time.perf_counter()
    embedding_profile = _resolve_embedding_profile(db, organization_id, filters, knowledge_base_ids)
    embedding = _embed_query(db, organization_id, query, embedding_profile)
    vector_literal = "[" + ",".join(str(value) for value in embedding) + "]"
    vector_candidates = _vector_search(
        db,
        organization_id,
        user_id,
        role,
        vector_literal,
        str(embedding_profile.id),
        knowledge_base_ids,
        filters,
    )
    vector_ms = int((time.perf_counter() - started) * 1000)
    keyword_started = time.perf_counter()
    keyword_candidates = _keyword_search(
        db, organization_id, user_id, role, query, knowledge_base_ids, filters
    )
    keyword_ms = int((time.perf_counter() - keyword_started) * 1000)
    rrf = reciprocal_rank_fusion(vector_candidates, keyword_candidates, filters.get("rrf_constant", 60))
    reranked = rerank_lexical(query, rrf[: filters.get("rerank_candidates", 20)], filters.get("max_chunks", 8))
    event = RetrievalEvent(
        organization_id=organization_id,
        user_id=user_id,
        chat_session_id=chat_session_id,
        original_query=query,
        rewritten_query=query.strip(),
        applied_filters={
            "knowledge_base_ids": knowledge_base_ids or [],
            "embedding_profile_id": str(embedding_profile.id),
            "embedding_model": embedding_profile.model_name,
            **filters,
        },
        vector_candidates=[_candidate_debug(candidate) for candidate in vector_candidates],
        keyword_candidates=[_candidate_debug(candidate) for candidate in keyword_candidates],
        rrf_ranking=[_candidate_debug(candidate) for candidate in rrf],
        reranker_scores=[
            {"chunk_id": candidate.chunk_id, "score": candidate.score, **candidate.metadata}
            for candidate in reranked
        ],
        final_context_chunks=[_candidate_debug(candidate) for candidate in reranked],
        token_usage={"estimated_context_tokens": sum(len(c.text.split()) for c in reranked)},
        latency_ms_by_stage={"vector": vector_ms, "keyword": keyword_ms},
    )
    db.add(event)
    if not debug:
        event.vector_candidates = []
        event.keyword_candidates = []
        event.rrf_ranking = []
        event.reranker_scores = []
    return reranked, event


def _access_clause() -> str:
    return """
      AND (
        NOT EXISTS (
          SELECT 1 FROM document_access_rules dar
          WHERE dar.organization_id = d.organization_id
            AND (dar.document_id = d.id OR dar.category_id = d.category_id)
            AND dar.permission = 'read'
        )
        OR EXISTS (
          SELECT 1 FROM document_access_rules dar
          WHERE dar.organization_id = d.organization_id
            AND (dar.document_id = d.id OR dar.category_id = d.category_id)
            AND dar.permission = 'read'
            AND (
              (dar.principal_type = 'user' AND dar.principal_id = CAST(:user_id AS text))
              OR (dar.principal_type = 'role' AND dar.principal_id = :role)
            )
        )
      )
    """


def _base_where(knowledge_base_ids: list[str] | None, filters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    clauses = ["d.deleted_at IS NULL"]
    params: dict[str, Any] = {}
    if knowledge_base_ids:
        clauses.append("CAST(c.knowledge_base_id AS text) = ANY(:knowledge_base_ids)")
        params["knowledge_base_ids"] = knowledge_base_ids
    if tags := filters.get("tags"):
        clauses.append("d.tags && :tags")
        params["tags"] = tags
    if confidentiality := filters.get("confidentiality"):
        clauses.append("d.confidentiality = :confidentiality")
        params["confidentiality"] = confidentiality
    if category_id := filters.get("category_id"):
        clauses.append("CAST(d.category_id AS text) = :category_id")
        params["category_id"] = category_id
    return " AND ".join(clauses), params


def _vector_search(
    db: Session,
    organization_id: UUID,
    user_id: UUID,
    role: str,
    vector_literal: str,
    embedding_profile_id: str,
    knowledge_base_ids: list[str] | None,
    filters: dict[str, Any],
) -> list[Candidate]:
    base_where, params = _base_where(knowledge_base_ids, filters)
    sql = text(
        f"""
        SELECT CAST(c.id AS text) AS chunk_id,
               CAST(d.id AS text) AS document_id,
               d.name AS document_name,
               c.text AS text,
               1 - (ev.embedding <=> CAST(:embedding AS vector)) AS score,
               jsonb_build_object(
                 'page_start', c.page_start,
                 'page_end', c.page_end,
                 'heading_hierarchy', c.heading_hierarchy,
                 'tags', c.tags,
                 'confidentiality', c.confidentiality
               ) AS metadata
        FROM chunks c
        JOIN embedding_vectors ev ON ev.chunk_id = c.id
        JOIN documents d ON d.id = c.document_id
        WHERE c.organization_id = :organization_id
          AND ev.embedding_profile_id = CAST(:embedding_profile_id AS uuid)
          AND {base_where}
          {_access_clause()}
        ORDER BY ev.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
        """
    )
    rows = db.execute(
        sql,
        {
            "organization_id": organization_id,
            "user_id": str(user_id),
            "role": role,
            "embedding": vector_literal,
            "embedding_profile_id": embedding_profile_id,
            "limit": filters.get("vector_candidate_count", 40),
            **params,
        },
    ).mappings()
    return [_row_to_candidate(row, "vector") for row in rows]


def _keyword_search(
    db: Session,
    organization_id: UUID,
    user_id: UUID,
    role: str,
    query: str,
    knowledge_base_ids: list[str] | None,
    filters: dict[str, Any],
) -> list[Candidate]:
    base_where, params = _base_where(knowledge_base_ids, filters)
    sql = text(
        f"""
        SELECT CAST(c.id AS text) AS chunk_id,
               CAST(d.id AS text) AS document_id,
               d.name AS document_name,
               c.text AS text,
               ts_rank_cd(to_tsvector('english', c.text), websearch_to_tsquery('english', :query)) AS score,
               jsonb_build_object(
                 'page_start', c.page_start,
                 'page_end', c.page_end,
                 'heading_hierarchy', c.heading_hierarchy,
                 'tags', c.tags,
                 'confidentiality', c.confidentiality
               ) AS metadata
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.organization_id = :organization_id
          AND {base_where}
          AND to_tsvector('english', c.text) @@ websearch_to_tsquery('english', :query)
          {_access_clause()}
        ORDER BY score DESC
        LIMIT :limit
        """
    )
    rows = db.execute(
        sql,
        {
            "organization_id": organization_id,
            "user_id": str(user_id),
            "role": role,
            "query": query,
            "limit": filters.get("keyword_candidate_count", 40),
            **params,
        },
    ).mappings()
    return [_row_to_candidate(row, "keyword") for row in rows]


def _row_to_candidate(row: Any, source: str) -> Candidate:
    return Candidate(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        document_name=row["document_name"],
        text=row["text"],
        score=float(row["score"] or 0),
        source=source,
        metadata=dict(row["metadata"] or {}),
    )


def _candidate_debug(candidate: Candidate) -> dict[str, Any]:
    return {
        "chunk_id": candidate.chunk_id,
        "document_id": candidate.document_id,
        "document_name": candidate.document_name,
        "score": candidate.score,
        "source": candidate.source,
        "preview": candidate.text[:280],
        "metadata": candidate.metadata,
    }


def _resolve_embedding_profile(
    db: Session,
    organization_id: UUID,
    filters: dict[str, Any],
    knowledge_base_ids: list[str] | None,
) -> EmbeddingProfile:
    ensure_default_profiles(db, organization_id)
    db.flush()
    profile_id = filters.get("embedding_profile_id")
    if not profile_id and knowledge_base_ids and len(knowledge_base_ids) == 1:
        try:
            kb = db.get(KnowledgeBase, UUID(str(knowledge_base_ids[0])))
        except ValueError:
            kb = None
        if (
            kb
            and kb.organization_id == organization_id
            and kb.deleted_at is None
            and kb.default_embedding_profile_id
        ):
            profile_id = kb.default_embedding_profile_id
    query = select(EmbeddingProfile).where(
        EmbeddingProfile.organization_id.in_([organization_id, None])
    )
    if profile_id:
        query = query.where(EmbeddingProfile.id == profile_id)
    else:
        query = query.where(EmbeddingProfile.is_active.is_(True)).order_by(
            EmbeddingProfile.organization_id.desc().nullslast(),
            EmbeddingProfile.created_at,
        )
    profile = db.scalar(query)
    if not profile:
        raise ValueError("Embedding profile not found.")
    return profile


def _embed_query(
    db: Session,
    organization_id: UUID,
    query: str,
    embedding_profile: EmbeddingProfile,
) -> list[float]:
    connection: ProviderConnection | None = None
    api_key: str | None = None
    if embedding_profile.provider.value != "Local":
        if not embedding_profile.provider_connection_id:
            raise ValueError("Embedding profile requires a provider connection.")
        connection = db.get(ProviderConnection, embedding_profile.provider_connection_id)
        if (
            not connection
            or connection.organization_id != organization_id
            or connection.deleted_at is not None
            or not connection.is_enabled
        ):
            raise ValueError("Embedding provider connection is not available.")
        api_key = decrypt_secret(connection.encrypted_api_key) if connection.encrypted_api_key else None
    provider = get_embedding_provider(
        embedding_profile.provider.value,
        model_name=embedding_profile.model_name,
        api_key=api_key,
        base_url=connection.base_url if connection else None,
        dimension=embedding_profile.embedding_dimension,
    )
    vectors = asyncio.run(provider.embed_texts([query]))
    vector = vectors[0] if vectors else []
    if len(vector) != embedding_profile.embedding_dimension:
        raise ValueError(
            f"Embedding provider returned {len(vector)} dimensions; "
            f"profile expects {embedding_profile.embedding_dimension}."
        )
    return vector
