# MCP Connectors

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
