# MCP Connectors

MCP connectors can run either through Streamable HTTP or through stdio commands. The stdio path accepts Cursor-style `mcpServers` JSON.

## Cursor-Style Stdio Config

Open `Settings -> Connectors`, choose `MCP server`, keep transport set to `Stdio`, and paste JSON like this:

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
  "name": "AWS API MCP",
  "is_enabled": true,
  "config": {
    "transport": "stdio",
    "mcpServers": {
      "awslabs.aws-api-mcp-server": {
        "command": "uvx",
        "args": ["awslabs.aws-api-mcp-server@latest"],
        "env": {
          "AWS_REGION": "us-east-1"
        },
        "disabled": false,
        "autoApprove": []
      }
    },
    "enabled_tool_names": [],
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

## Streamable HTTP

For hosted MCP servers, choose transport `Streamable HTTP`, set the MCP endpoint as the connector base URL, and optionally set a bearer token in `Secret`. The backend initializes the MCP session and calls JSON-RPC methods against the endpoint.

## Chat Usage

After saving and testing an MCP connector, open Chat, enable `MCP Tools`, and select the connector. Only read-only tools are called by default. Tool names can be limited with `enabled_tool_names`, and tool tags can mark tools for `web_search` or `knowledge_lookup`.
