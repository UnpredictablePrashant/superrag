import asyncio

from app.models.entities import PipelineStage
from app.services.embeddings import cosine_similarity, deterministic_embedding
from app.services.eta import StageWork, estimate_completion_seconds, update_ema
from app.services.pipeline import (
    _document_warnings,
    _has_quality_review_override,
    _is_embedding_backfill,
    _terminal_stage,
)
from app.services.providers import embedding_dimension_for_model, infer_capability
from app.services.retrieval import (
    Candidate,
    _apply_similarity_threshold,
    _base_where,
    reciprocal_rank_fusion,
    rerank_lexical,
)


def test_deterministic_embeddings_are_stable_and_semantic_enough() -> None:
    left = deterministic_embedding("annual leave policy")
    again = deterministic_embedding("annual leave policy")
    right = deterministic_embedding("database recovery runbook")
    assert left == again
    assert cosine_similarity(left, again) > cosine_similarity(left, right)


def test_provider_capability_infers_openai_embedding_dimensions() -> None:
    capability = infer_capability("OpenAI", "text-embedding-3-large")

    assert capability.supports_embeddings
    assert not capability.supports_chat
    assert embedding_dimension_for_model("OpenAI", "text-embedding-3-large") == 3072


def test_local_embedding_provider_can_use_profile_dimension() -> None:
    from app.services.embeddings import get_embedding_provider

    provider = get_embedding_provider("Local", dimension=384)
    vectors = asyncio.run(provider.embed_texts(["annual leave policy"]))

    assert len(vectors) == 1
    assert len(vectors[0]) == 384


def test_pipeline_embedding_backfill_mode_is_explicit() -> None:
    class Run:
        retrieval_index_config = {"migration_mode": "embedding_backfill"}

    assert _is_embedding_backfill(Run())


def test_pipeline_waits_for_review_instead_of_reporting_complete() -> None:
    class RunDoc:
        document_id = "00000000-0000-0000-0000-000000000001"
        status = PipelineStage.AWAITING_REVIEW
        warnings = []

    run_docs = [RunDoc()]

    assert _terminal_stage(run_docs) == PipelineStage.AWAITING_REVIEW
    assert _document_warnings(run_docs)[0]["code"] == "awaiting_review"


def test_quality_review_override_is_scoped_to_current_version() -> None:
    class Document:
        version_number = 2
        checksum = "abc123"
        custom_metadata = {
            "quality_review_override": {
                "version_number": 2,
                "checksum": "abc123",
            }
        }

    assert _has_quality_review_override(Document())

    Document.version_number = 3

    assert not _has_quality_review_override(Document())


def test_rrf_merges_vector_and_keyword_rankings() -> None:
    vector = [
        Candidate("a", "d1", "Doc", "leave policy", 0.9, "vector", {}),
        Candidate("b", "d2", "Doc", "remote work", 0.8, "vector", {}),
    ]
    keyword = [
        Candidate("b", "d2", "Doc", "remote work", 0.7, "keyword", {}),
        Candidate("c", "d3", "Doc", "security policy", 0.6, "keyword", {}),
    ]
    fused = reciprocal_rank_fusion(vector, keyword, k=60)
    assert {candidate.chunk_id for candidate in fused} == {"a", "b", "c"}
    assert fused[0].chunk_id == "b"


def test_similarity_threshold_filters_vector_candidates() -> None:
    candidates = [
        Candidate("a", "d1", "Doc", "leave policy", 0.35, "vector", {}),
        Candidate("b", "d2", "Doc", "security policy", 0.05, "vector", {}),
    ]

    filtered = _apply_similarity_threshold(candidates, 0.1)

    assert [candidate.chunk_id for candidate in filtered] == ["a"]


def test_retrieval_where_clause_only_uses_indexed_documents() -> None:
    base_where, _ = _base_where(None, {})

    assert "d.processing_status IN ('COMPLETED', 'COMPLETED_WITH_WARNINGS')" in base_where


def test_local_reranker_boosts_query_overlap() -> None:
    candidates = [
        Candidate("a", "d1", "Doc", "database backup procedure", 0.1, "hybrid", {}),
        Candidate("b", "d2", "Doc", "annual leave request policy", 0.1, "hybrid", {}),
    ]
    reranked = rerank_lexical("leave policy", candidates)
    assert reranked[0].chunk_id == "b"


def test_eta_uses_observed_throughput_and_ema() -> None:
    assert update_ema(10, 20) == 13.5
    seconds, confidence = estimate_completion_seconds(
        5,
        [StageWork("embedding", remaining_units=100, observed_units_per_second=10, historical_units_per_second=None)],
    )
    assert seconds == 15
    assert confidence == "High"
