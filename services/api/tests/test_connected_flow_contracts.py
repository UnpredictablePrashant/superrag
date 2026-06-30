from app.api.routes.chat import _resolve_answer_mode
from app.api.routes.workspace import _available_answer_modes, _chat_model_summary
from app.schemas.api import ChatMessageCreateIn, ConnectorSyncIn
from app.services.connectors import _configured_mcp_tool_names, _connector_supports_web_search
from app.services.document_ingestion import apply_retrieval_defaults


class Connection:
    def __init__(self, kind: str, config: dict):
        self.kind = kind
        self.config = config


def test_answer_mode_company_data_uses_indexed_scope_only() -> None:
    mode, use_web, use_mcp, indexed_scope = _resolve_answer_mode(
        ChatMessageCreateIn(content="What is our leave policy?", answer_mode="company_data")
    )

    assert mode == "company_data"
    assert not use_web
    assert not use_mcp
    assert indexed_scope


def test_answer_mode_live_web_does_not_silently_blend_indexed_data() -> None:
    mode, use_web, use_mcp, indexed_scope = _resolve_answer_mode(
        ChatMessageCreateIn(content="Search latest docs", answer_mode="live_web")
    )

    assert mode == "live_web"
    assert use_web
    assert not use_mcp
    assert not indexed_scope


def test_legacy_live_booleans_remain_blended_for_backwards_compatibility() -> None:
    mode, use_web, use_mcp, indexed_scope = _resolve_answer_mode(
        ChatMessageCreateIn(content="Search tools", use_mcp_tools=True)
    )

    assert mode == "blended"
    assert not use_web
    assert use_mcp
    assert indexed_scope


def test_connector_web_search_capability_uses_configured_tool_tags() -> None:
    config = {
        "enabled_tool_names": ["lookup_policy"],
        "tool_tags": {"lookup_policy": ["knowledge_lookup"], "search_web": ["web_search"]},
    }

    assert _configured_mcp_tool_names(config) == {"lookup_policy", "search_web"}
    assert _connector_supports_web_search(Connection("mcp", config), {"lookup_policy", "search_web"})


def test_workspace_modes_reflect_indexed_and_live_source_readiness() -> None:
    modes = _available_answer_modes(
        3,
        [{"web_search_supported": True, "live_tools_supported": True}],
    )

    assert modes == ["company_data", "live_web", "mcp_tools", "blended"]


def test_workspace_chat_model_summary_does_not_report_embedding_fallback() -> None:
    summary = _chat_model_summary(None)

    assert summary["provider"] == "LLM"
    assert summary["model_name"] == "not configured"


def test_connector_sync_contract_carries_retrieval_index_config() -> None:
    payload = ConnectorSyncIn(
        knowledge_base_id="00000000-0000-0000-0000-000000000001",
        retrieval_index_config={
            "retrieval_algorithm": "hybrid_rrf",
            "max_chunks": 10,
            "vector_candidate_count": 50,
            "keyword_candidate_count": 30,
        },
    )

    assert payload.retrieval_index_config["retrieval_algorithm"] == "hybrid_rrf"
    assert payload.retrieval_index_config["vector_candidate_count"] == 50


def test_pipeline_retrieval_config_becomes_kb_default() -> None:
    class KnowledgeBase:
        default_retrieval_config = {"max_chunks": 8, "rrf_constant": 60}

    kb = KnowledgeBase()

    apply_retrieval_defaults(
        kb,  # type: ignore[arg-type]
        {
            "retrieval_algorithm": "vector",
            "max_chunks": 12,
            "vector_candidate_count": 80,
            "source": "data_hub_reindex",
        },
    )

    assert kb.default_retrieval_config == {
        "retrieval_algorithm": "vector",
        "max_chunks": 12,
        "rrf_constant": 60,
        "vector_candidate_count": 80,
    }
