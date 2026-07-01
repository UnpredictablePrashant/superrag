from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.api.deps import AuthContext
from app.api.routes.mcp import create_mcp_setup
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


def test_mcp_setup_generates_hosted_config_for_current_user() -> None:
    class FakeDb:
        def __init__(self) -> None:
            self.added = []
            self.committed = False

        def add(self, item) -> None:
            self.added.append(item)

        def commit(self) -> None:
            self.committed = True

    organization_id = uuid4()
    user_id = uuid4()
    ctx = AuthContext(
        user=SimpleNamespace(id=user_id),
        organization=SimpleNamespace(id=organization_id),
        role="Member",
        session=SimpleNamespace(),
    )
    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"user-agent": "pytest"},
    )
    db = FakeDb()

    setup = create_mcp_setup(request, client="cursor", ctx=ctx, db=db)  # type: ignore[arg-type]

    assert setup["mcp_url"].endswith("/mcp")
    assert setup["token"]
    assert setup["cursor_config"]["mcpServers"]["rag-console"]["url"] == setup["mcp_url"]
    assert setup["cursor_config"]["mcpServers"]["rag-console"]["headers"]["Authorization"] == f"Bearer {setup['token']}"
    assert db.committed
    assert db.added[0].user_id == user_id
    assert db.added[0].organization_id == organization_id
