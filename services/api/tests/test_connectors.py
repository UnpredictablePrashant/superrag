from app.services.connectors import (
    _connector_supports_web_search,
    _mcp_http_server_config,
    _mcp_stdio_server_config,
    _mcp_transport,
    is_mcp_tool_read_only,
    normalize_connector_config,
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


def test_mcp_cursor_style_http_config_uses_streamable_http() -> None:
    class Connection:
        base_url = None
        config = {
            "mcpServers": {
                "n8n-mcp": {
                    "type": "http",
                    "url": "https://example.app.n8n.cloud/mcp-server/http",
                    "headers": {"X-Test": "ok"},
                }
            }
        }

    assert _mcp_transport(Connection()) == "streamable_http"
    config = _mcp_http_server_config(Connection())
    assert config.name == "n8n-mcp"
    assert config.url == "https://example.app.n8n.cloud/mcp-server/http"
    assert config.headers == {"X-Test": "ok"}


def test_mcp_http_config_extracts_bearer_token_to_secret() -> None:
    base_url, config, secret = normalize_connector_config(
        kind="mcp",
        base_url=None,
        secret=None,
        config={
            "mcpServers": {
                "n8n-mcp": {
                    "type": "http",
                    "url": "https://example.app.n8n.cloud/mcp-server/http",
                    "headers": {"Authorization": "Bearer secret-token"},
                }
            }
        },
    )

    assert base_url == "https://example.app.n8n.cloud/mcp-server/http"
    assert config["transport"] == "streamable_http"
    assert config["headers"] == {}
    assert config["mcpServers"]["n8n-mcp"]["headers"] == {}
    assert secret == "secret-token"

    _, config, secret = normalize_connector_config(
        kind="mcp",
        base_url=None,
        secret="existing-secret",
        config={
            "mcpServers": {
                "n8n-mcp": {
                    "type": "http",
                    "url": "https://example.app.n8n.cloud/mcp-server/http",
                    "headers": {"Authorization": "Bearer config-token"},
                }
            }
        },
    )

    assert config["headers"] == {}
    assert config["mcpServers"]["n8n-mcp"]["headers"] == {}
    assert secret == "existing-secret"


def test_mcp_tool_filtering_respects_disabled_tools() -> None:
    tool = {"name": "lookup_policy", "description": "Lookup policy"}

    assert not should_use_mcp_tool(
        tool,
        {"disabled_tool_names": ["lookup_policy"]},
        use_web_search=False,
        use_mcp_tools=True,
    )


def test_mcp_web_search_capability_requires_search_tool() -> None:
    class Connection:
        kind = "mcp"
        config = {}

    assert not _connector_supports_web_search(Connection(), set())

    Connection.config = {"discovered_tools": [{"name": "search_web"}]}
    assert _connector_supports_web_search(Connection(), set())
