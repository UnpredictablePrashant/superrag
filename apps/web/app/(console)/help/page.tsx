import { Badge, Panel } from "@rag-console/ui";
import { Bot, CheckCircle2, KeyRound, Plug, ShieldCheck, TerminalSquare } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

const mcpConfig = `{
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
}`;

const mcpApiPayload = `{
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
}`;

export default function DocsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-zinc-950">Docs</h2>
        <p className="mt-1 text-sm text-zinc-500">Setup references for integrations and live tool connectors.</p>
      </div>

      <div className="grid gap-4 xl:grid-cols-[260px_1fr]">
        <Panel className="h-fit p-4">
          <nav className="space-y-2 text-sm">
            <a href="#telegram" className="flex items-center gap-2 rounded-md px-3 py-2 font-medium text-zinc-700 hover:bg-zinc-100">
              <Bot className="h-4 w-4 text-sky-700" aria-hidden />
              Telegram
            </a>
            <a href="#mcp" className="flex items-center gap-2 rounded-md px-3 py-2 font-medium text-zinc-700 hover:bg-zinc-100">
              <Plug className="h-4 w-4 text-emerald-700" aria-hidden />
              MCP connectors
            </a>
          </nav>
        </Panel>

        <div className="space-y-5">
          <Panel id="telegram" className="scroll-mt-24 p-5">
            <div className="flex flex-wrap items-center gap-2">
              <Bot className="h-5 w-5 text-sky-700" aria-hidden />
              <h3 className="font-semibold text-zinc-950">Telegram Integration</h3>
              <Badge tone="blue">Bot webhook</Badge>
            </div>
            <p className="mt-3 text-sm leading-6 text-zinc-600">
              Telegram lets approved users add content to a default knowledge base and ask grounded questions with
              `/ask`.
            </p>

            <DocGrid
              items={[
                "Set API_BASE_URL to the public HTTPS API URL that Telegram can reach.",
                "Create a Telegram bot with @BotFather and copy the bot token.",
                "Create an LLM chat model profile before enabling answer/refine actions.",
                "Add an OpenAI provider connection if voice transcription should be enabled.",
              ]}
            />

            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              <DocBlock title="Console Flow" icon={CheckCircle2}>
                <ol className="list-decimal space-y-2 pl-5 text-sm leading-6 text-zinc-600">
                  <li>
                    Open <Link className="font-medium text-emerald-700 hover:underline" href="/settings">Settings</Link>
                    , add an AI provider, and create a model profile.
                  </li>
                  <li>Open Settings, Telegram, paste the bot token, choose the default knowledge base and model.</li>
                  <li>Save, test the bot, then register the webhook.</li>
                  <li>Add allowed Telegram users by username, phone number, or Telegram user ID.</li>
                </ol>
              </DocBlock>
              <DocBlock title="Webhook" icon={KeyRound}>
                <CodeBlock value="{API_BASE_URL}/api/integrations/telegram/webhook/{integration_id}" />
                <p className="mt-3 text-sm leading-6 text-zinc-600">
                  The app sends Telegram the integration webhook secret during registration and verifies it on inbound
                  updates.
                </p>
              </DocBlock>
            </div>

            <div className="mt-5 rounded-md bg-zinc-50 p-4">
              <p className="font-medium text-zinc-950">Commands</p>
              <CodeBlock value={"/help\n/add your note\n/ask your question"} />
            </div>
          </Panel>

          <Panel id="mcp" className="scroll-mt-24 p-5">
            <div className="flex flex-wrap items-center gap-2">
              <Plug className="h-5 w-5 text-emerald-700" aria-hidden />
              <h3 className="font-semibold text-zinc-950">MCP Connectors</h3>
              <Badge tone="green">Cursor-style JSON</Badge>
            </div>
            <p className="mt-3 text-sm leading-6 text-zinc-600">
              MCP connectors support Streamable HTTP and stdio. Paste a Cursor-style `mcpServers` config and the app
              detects the server, transport, and available tools when you test the connector.
            </p>

            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              <DocBlock title="Settings Form" icon={TerminalSquare}>
                <ol className="list-decimal space-y-2 pl-5 text-sm leading-6 text-zinc-600">
                  <li>Open Settings, Connectors.</li>
                  <li>Choose MCP server and paste the Cursor MCP JSON into the Cursor MCP JSON field.</li>
                  <li>Save, test, then use the detected tool toggles to keep tools active or inactive.</li>
                  <li>Pause or enable the MCP source from the connector list. Enable MCP Tools in Chat when you want live calls.</li>
                </ol>
              </DocBlock>
              <DocBlock title="Production Guardrail" icon={ShieldCheck}>
                <p className="text-sm leading-6 text-zinc-600">
                  In production, stdio commands must be allowlisted with `MCP_STDIO_ALLOWLIST`. Prefer instance roles,
                  workload identity, or short-lived credentials over long-lived secrets in connector config.
                </p>
                <CodeBlock value="MCP_STDIO_ALLOWLIST=uvx,uvx awslabs.aws-api-mcp-server@latest" />
              </DocBlock>
            </div>

            <div className="mt-5 space-y-4">
              <div>
                <p className="mb-2 font-medium text-zinc-950">Hosted MCP JSON</p>
                <CodeBlock value={mcpConfig} />
              </div>
              <div>
                <p className="mb-2 font-medium text-zinc-950">API Payload</p>
                <CodeBlock value={mcpApiPayload} />
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function DocGrid({ items }: { items: string[] }) {
  return (
    <div className="mt-5 grid gap-3 md:grid-cols-2">
      {items.map((item) => (
        <div key={item} className="rounded-md border border-zinc-200 p-3 text-sm leading-6 text-zinc-600">
          {item}
        </div>
      ))}
    </div>
  );
}

function DocBlock({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: LucideIcon;
  children: ReactNode;
}) {
  return (
    <div className="rounded-md border border-zinc-200 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Icon className="h-4 w-4 text-zinc-700" aria-hidden />
        <p className="font-medium text-zinc-950">{title}</p>
      </div>
      {children}
    </div>
  );
}

function CodeBlock({ value }: { value: string }) {
  return (
    <pre className="mt-2 overflow-auto rounded-md bg-zinc-950 p-3 text-xs leading-5 text-zinc-50">
      <code>{value}</code>
    </pre>
  );
}
