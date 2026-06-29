from app.services.connectors import (
    _mcp_stdio_server_config,
    is_mcp_tool_read_only,
    normalize_web_document,
    select_mcp_tool_arguments,
    should_use_mcp_tool,
)


def test_web_connector_normalizes_html_document() -> None:
    document = normalize_web_document(
        b"<html><head><title>Unitus Capital</title></head><body>Impact finance</body></html>",
        "https://unitus.example/about",
    )

    assert document.title == "Unitus Capital"
    assert document.filename == "Unitus-Capital.html"
    assert document.external_id == "https://unitus.example/about"
    assert document.metadata["source_type"] == "synced_web"


def test_mcp_tool_argument_selection_prefers_declared_query_field() -> None:
    tool = {"inputSchema": {"properties": {"q": {"type": "string"}}}}

    assert select_mcp_tool_arguments(tool, "portfolio companies") == {"q": "portfolio companies"}


def test_mcp_live_tool_filtering_uses_tags_and_read_only_annotations() -> None:
    tool = {
        "name": "search_web",
        "description": "Search the public web",
        "annotations": {"readOnlyHint": True},
    }

    assert should_use_mcp_tool(tool, {}, use_web_search=True, use_mcp_tools=False)
    assert is_mcp_tool_read_only(tool)


def test_mcp_live_tool_filtering_rejects_write_like_tools() -> None:
    tool = {"name": "delete_document", "description": "Delete a document"}

    assert not is_mcp_tool_read_only(tool)


def test_mcp_stdio_config_accepts_cursor_style_mcp_servers() -> None:
    class Connection:
        config = {
            "mcpServers": {
                "awslabs.aws-api-mcp-server": {
                    "command": "uvx",
                    "args": ["awslabs.aws-api-mcp-server@latest"],
                    "env": {"AWS_REGION": "us-east-1"},
                    "disabled": False,
                    "autoApprove": [],
                }
            }
        }

    config = _mcp_stdio_server_config(Connection())

    assert config.name == "awslabs.aws-api-mcp-server"
    assert config.command == ["uvx", "awslabs.aws-api-mcp-server@latest"]
    assert config.env == {"AWS_REGION": "us-east-1"}


def test_mcp_stdio_config_skips_disabled_cursor_servers() -> None:
    class Connection:
        config = {
            "mcpServers": {
                "disabled-server": {"command": "uvx", "args": ["disabled"], "disabled": True},
                "enabled-server": {"command": "node", "args": ["server.js"], "disabled": False},
            }
        }

    config = _mcp_stdio_server_config(Connection())

    assert config.name == "enabled-server"
    assert config.command == ["node", "server.js"]
