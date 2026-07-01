from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID

from app.mcp_server import _bounded_limit, _to_jsonable, create_mcp_server


def test_mcp_server_exposes_rag_tools() -> None:
    async def list_tool_names() -> list[str]:
        server = create_mcp_server(require_http_auth=False)
        tools = await server.list_tools()
        return [tool.name for tool in tools]

    assert asyncio.run(list_tool_names()) == [
        "rag_workspace_summary",
        "rag_list_knowledge_bases",
        "rag_list_documents",
        "rag_get_document_preview",
        "rag_search",
        "rag_ask",
    ]


def test_mcp_json_helpers_prepare_tool_payloads() -> None:
    value = {
        "id": UUID("00000000-0000-0000-0000-000000000001"),
        "created_at": datetime(2026, 7, 1, 8, 30),
    }

    assert _to_jsonable(value) == {
        "id": "00000000-0000-0000-0000-000000000001",
        "created_at": "2026-07-01T08:30:00",
    }
    assert _bounded_limit(500, 20) == 20
    assert _bounded_limit(0, 20) == 1
