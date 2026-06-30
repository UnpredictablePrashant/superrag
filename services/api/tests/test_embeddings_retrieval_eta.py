import asyncio

from app.services.embeddings import cosine_similarity, deterministic_embedding
from app.services.eta import StageWork, estimate_completion_seconds, update_ema
from app.services.pipeline import _is_embedding_backfill
from app.services.providers import embedding_dimension_for_model, infer_capability
from app.services.retrieval import (
    Candidate,
    _apply_similarity_threshold,
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
