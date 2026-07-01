# MCP Connectors

This product can use external MCP servers as connectors, and it can also expose the RAG workspace itself as an MCP server for assistants such as Claude, Cursor, and other MCP-compatible clients.

## Expose RAG Console as an MCP Server

The API mounts a Streamable HTTP MCP endpoint at:

```text
http://localhost:8000/mcp
```

In production, replace `localhost:8000` with the public API origin. The MCP server authenticates each user with the same RAG Console session token used by the web app. For HTTP clients, send it as a bearer token:

```http
Authorization: Bearer <rag_console_session_token>
```

For stdio clients, pass it through `RAG_CONSOLE_SESSION_TOKEN`.

### Available RAG Tools

External assistants discover these tools:

| Tool | Purpose |
| --- | --- |
| `rag_workspace_summary` | Show organization, document, knowledge base, and indexed-document counts. |
| `rag_list_knowledge_bases` | List available knowledge bases and retrieval defaults. |
| `rag_list_documents` | List documents by knowledge base, search text, status, and limit. |
| `rag_get_document_preview` | Read the cleaned or latest derived preview text for a document. |
| `rag_search` | Search indexed enterprise content and return source chunks. |
| `rag_ask` | Ask a grounded question over enterprise content and return answer plus citations. |

All tools are scoped to the authenticated user's organization and role. Search and answer tools reuse the same retrieval permissions as in-app chat.

### Cursor HTTP Config

Use this when Cursor can reach your hosted API directly:

```json
{
  "mcpServers": {
    "rag-console": {
      "type": "http",
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer <rag_console_session_token>"
      }
    }
  }
}
```

### Claude or Cursor Stdio Config

Use this when the assistant runs on the same machine as the API project. Run it from `services/api` so the Python module path resolves:

```json
{
  "mcpServers": {
    "rag-console": {
      "command": "python",
      "args": ["-m", "app.mcp_server"],
      "env": {
        "PYTHONPATH": "<absolute_path_to_enterpriserag>/services/api",
        "RAG_CONSOLE_SESSION_TOKEN": "<rag_console_session_token>",
        "DATABASE_URL": "postgresql+psycopg2://rag:rag@localhost:5432/rag_console"
      }
    }
  }
}
```

To run a standalone HTTP MCP process instead of the API-mounted endpoint:

```powershell
cd services/api
python -m app.mcp_server --transport streamable-http --host 0.0.0.0 --port 8010 --path /mcp
```

Then configure the client URL as `http://localhost:8010/mcp`.

## Use External MCP Servers as Connectors

MCP connectors can run either through Streamable HTTP or through stdio commands. Paste Cursor-style `mcpServers` JSON and the API infers the transport, selects the first non-disabled server, and discovers tools when the connector is tested.

## Hosted HTTP Config

Hosted MCP servers such as n8n can be added with their HTTP endpoint directly in `mcpServers`:

```json
{
  "mcpServers": {
    "n8n-mcp": {
      "type": "http",
      "url": "https://your-workspace.app.n8n.cloud/mcp-server/http",
      "headers": {
        "Authorization": "Bearer <token>"
      },
      "disabled": false
    }
  }
}
```

If an `Authorization: Bearer ...` header is present, the API extracts it into the connector secret and stores only the non-secret config.

## Cursor-Style Stdio Config

Open `Settings -> Connectors`, choose `MCP server`, and paste JSON like this. The app detects this as stdio from the command-based server entry:

```json
{
  "mcpServers": {
    "awslabs.aws-api-mcp-server": {
      "command": "uvx",
      "args": [
        "awslabs.aws-api-mcp-server@latest"
      ],
      "env": {
        "AWS_REGION": "us-east-1"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

The backend turns that into the stdio command:

```text
uvx awslabs.aws-api-mcp-server@latest
```

and passes the `env` object to the MCP process.

If the JSON contains more than one server, the first non-disabled server is used. To choose a specific server, add `mcp_server_name` at the top level:

```json
{
  "mcp_server_name": "awslabs.aws-api-mcp-server",
  "mcpServers": {
    "awslabs.aws-api-mcp-server": {
      "command": "uvx",
      "args": ["awslabs.aws-api-mcp-server@latest"],
      "env": {
        "AWS_REGION": "us-east-1"
      },
      "disabled": false
    }
  }
}
```

## API Payload

You can create the same connector directly through the API:

```json
{
  "kind": "mcp",
  "scope": "organization",
  "name": "n8n MCP",
  "is_enabled": true,
  "config": {
    "mcpServers": {
      "n8n-mcp": {
        "type": "http",
        "url": "https://your-workspace.app.n8n.cloud/mcp-server/http",
        "headers": {
          "Authorization": "Bearer <token>"
        },
        "disabled": false
      }
    },
    "disabled_tool_names": [],
    "tool_tags": {}
  }
}
```

## Production Allowlist

In production, stdio commands must be allowlisted with `MCP_STDIO_ALLOWLIST`. You can allow either the executable or the full command string:

```env
MCP_STDIO_ALLOWLIST=uvx,uvx awslabs.aws-api-mcp-server@latest
```

Connector `config` is stored as connector configuration, so avoid putting long-lived secrets directly in `mcpServers.env`. Prefer instance roles, workload identity, short-lived credentials, or environment already available to the API container.

## Chat Usage

After saving and testing an MCP connector, open Chat, enable `MCP Tools`, and select the connector. Testing caches the detected tools on the connector. Tools are active by default; turn individual tools off with the detected tool toggles, which writes `disabled_tool_names` into connector config. Tool tags can still mark tools for `web_search` or `knowledge_lookup`.
