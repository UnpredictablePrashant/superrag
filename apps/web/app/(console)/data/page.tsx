"use client";

import { EmptyState } from "@/components/empty-state";
import { ErrorBox } from "@/components/error-box";
import { StatusBadge } from "@/components/status-badge";
import {
  api,
  ConnectorConnection,
  ConnectorItem,
  ConnectorRun,
  createPipelineRun,
  deleteDocument,
  getCompanyProfile,
  getDocumentQualityReport,
  getTelegramIntegration,
  getWorkspaceSummary,
  listCompanyProfiles,
  listConnectorItems,
  listConnectorRuns,
  listConnectors,
  listDocuments,
  listKnowledgeBases,
  listMembers,
  listProfiles,
  previewDocument,
  replaceDocumentFile,
  listTelegramAllowedUsers,
  listTelegramMessages,
  reviewDocument,
  TelegramAllowedUser,
  TelegramIntegration,
  TelegramMessageLog,
  updateDocument,
  uploadDocument,
} from "@/lib/api";
import { formatBytes, shortDate } from "@/lib/format";
import type { Confidentiality, DocumentRecord, KnowledgeBase } from "@rag-console/shared-types";
import { Badge, Button, Input, Label, Panel, Select, Textarea } from "@rag-console/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  Bot,
  Building2,
  Check,
  Database,
  Eye,
  FileUp,
  FileText,
  Globe,
  History,
  Pencil,
  Play,
  Plug,
  RefreshCw,
  RotateCw,
  Save,
  Search,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

const DEFAULT_MCP_CONFIG = `{
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

export default function DataHubPage() {
  const queryClient = useQueryClient();
  const [selectedKbId, setSelectedKbId] = React.useState("");
  const [activeConnectionId, setActiveConnectionId] = React.useState("");
  const [selectedReviewDocId, setSelectedReviewDocId] = React.useState("");
  const [selectedCompanyId, setSelectedCompanyId] = React.useState("");
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");

  const summary = useQuery({ queryKey: ["workspace-summary"], queryFn: getWorkspaceSummary, refetchInterval: 10000 });
  const kbs = useQuery({ queryKey: ["knowledge-bases"], queryFn: listKnowledgeBases });
  const docs = useQuery({ queryKey: ["documents", selectedKbId], queryFn: () => listDocuments(selectedKbId || undefined) });
  const connectors = useQuery({ queryKey: ["connectors"], queryFn: listConnectors, refetchInterval: 10000 });
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: listProfiles });
  const connectorRuns = useQuery({
    queryKey: ["connector-runs", activeConnectionId],
    enabled: Boolean(activeConnectionId),
    queryFn: () => listConnectorRuns(activeConnectionId),
    refetchInterval: 5000,
  });
  const connectorItems = useQuery({
    queryKey: ["connector-items", activeConnectionId],
    enabled: Boolean(activeConnectionId),
    queryFn: () => listConnectorItems(activeConnectionId),
  });
  const qualityReport = useQuery({
    queryKey: ["document-quality", selectedReviewDocId],
    enabled: Boolean(selectedReviewDocId),
    queryFn: () => getDocumentQualityReport(selectedReviewDocId),
  });
  const companyProfiles = useQuery({ queryKey: ["company-profiles"], queryFn: () => listCompanyProfiles() });
  const companyDetail = useQuery({
    queryKey: ["company-profile", selectedCompanyId],
    enabled: Boolean(selectedCompanyId),
    queryFn: () => getCompanyProfile(selectedCompanyId),
  });

  React.useEffect(() => {
    const defaultKbId = summary.data?.default_knowledge_base?.id ?? kbs.data?.[0]?.id;
    if (!selectedKbId && defaultKbId) setSelectedKbId(defaultKbId);
  }, [kbs.data, selectedKbId, summary.data?.default_knowledge_base?.id]);

  async function testConnector(connection: ConnectorConnection) {
    setError("");
    setNotice("");
    try {
      const result = await api<{ status: string; message?: string; tools?: McpToolSummary[] }>(`/connectors/${connection.id}/test`, { method: "POST" });
      setNotice(result.status === "ok" ? `Connector test passed. Detected ${result.tools?.length ?? 0} tool(s).` : result.message ?? "Connector test failed.");
      queryClient.invalidateQueries({ queryKey: ["connectors"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connector test failed.");
    }
  }

  async function toggleConnector(connection: ConnectorConnection) {
    setError("");
    setNotice("");
    try {
      await api(`/connectors/${connection.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_enabled: !connection.is_enabled }),
      });
      setNotice(connection.is_enabled ? "Source paused." : "Source enabled.");
      queryClient.invalidateQueries({ queryKey: ["connectors"] });
      queryClient.invalidateQueries({ queryKey: ["workspace-summary"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update source.");
    }
  }

  async function toggleTool(connection: ConnectorConnection, toolName: string) {
    setError("");
    setNotice("");
    try {
      const disabled = stringList(connection.config.disabled_tool_names);
      const nextDisabled = disabled.includes(toolName)
        ? disabled.filter((name) => name !== toolName)
        : [...disabled, toolName];
      await api(`/connectors/${connection.id}`, {
        method: "PATCH",
        body: JSON.stringify({ config: { ...connection.config, disabled_tool_names: nextDisabled } }),
      });
      queryClient.invalidateQueries({ queryKey: ["connectors"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update tool.");
    }
  }

  async function syncConnector(connection: ConnectorConnection) {
    setError("");
    setNotice("");
    if (!selectedKbId) {
      setError("Choose a knowledge base before syncing.");
      return;
    }
    try {
      await api(`/connectors/${connection.id}/sync`, {
        method: "POST",
        body: JSON.stringify({
          knowledge_base_id: selectedKbId,
          share_with_organization: connection.scope === "organization",
        }),
      });
      setActiveConnectionId(connection.id);
      setNotice("Source sync queued.");
      queryClient.invalidateQueries({ queryKey: ["connector-runs", connection.id] });
      queryClient.invalidateQueries({ queryKey: ["workspace-summary"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sync connector.");
    }
  }

  async function review(doc: DocumentRecord, action: "continue_unchanged" | "exclude_document") {
    setError("");
    try {
      await reviewDocument(doc.id, action);
      setNotice(action === "exclude_document" ? "Document excluded from ingestion." : "Document returned to ingestion.");
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["workspace-summary"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update review item.");
    }
  }

  const allDocs = docs.data ?? [];
  const reviewDocs = allDocs.filter((doc) => ["AWAITING_REVIEW", "FAILED"].includes(doc.processing_status));
  const activeConnection = (connectors.data ?? []).find((connection) => connection.id === activeConnectionId);

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-3 xl:flex-row xl:items-end">
        <div>
          <h2 className="text-2xl font-semibold text-zinc-950">Data Hub</h2>
          <p className="mt-1 text-sm text-zinc-500">Connect sources, index company data, and keep answer readiness healthy.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href="/ask">
            <Button>
              <Search className="h-4 w-4" aria-hidden />
              Try Ask
            </Button>
          </Link>
          <Link href="/activity">
            <Button variant="secondary">
              <History className="h-4 w-4" aria-hidden />
              Activity
            </Button>
          </Link>
          <Select className="w-64" value={selectedKbId} onChange={(event) => setSelectedKbId(event.target.value)}>
            <option value="">Select knowledge base</option>
            {(kbs.data ?? []).map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <ErrorBox message={error} />
      {notice ? <div className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</div> : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <HubStat label="Indexed docs" value={summary.data?.indexed_document_count ?? 0} icon={Archive} />
        <HubStat label="Active sources" value={summary.data?.active_source_count ?? 0} icon={Plug} />
        <HubStat label="Review items" value={summary.data?.review_item_count ?? 0} icon={RefreshCw} />
        <HubStat label="Failed syncs" value={summary.data?.failed_sync_count ?? 0} icon={X} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_0.95fr]">
        <SourceBuilder
          knowledgeBases={kbs.data ?? []}
          selectedKbId={selectedKbId}
          setSelectedKbId={setSelectedKbId}
          onError={setError}
          onNotice={setNotice}
        />
        <SourcesPanel
          connectors={connectors.data ?? []}
          activeConnectionId={activeConnectionId}
          setActiveConnectionId={setActiveConnectionId}
          onTest={testConnector}
          onSync={syncConnector}
          onToggle={toggleConnector}
          onToggleTool={toggleTool}
        />
      </div>

      <TelegramSourcePanel
        knowledgeBases={kbs.data ?? []}
        selectedKbId={selectedKbId}
        profiles={profiles.data}
        onError={setError}
        onNotice={setNotice}
      />

      {activeConnection ? (
        <ConnectorDetailPanel connection={activeConnection} runs={connectorRuns.data ?? []} items={connectorItems.data ?? []} />
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[1fr_0.95fr]">
        <KnowledgePanel
          docs={allDocs}
          kbs={kbs.data ?? []}
          selectedKbId={selectedKbId}
          setSelectedKbId={setSelectedKbId}
        />
        <ReviewPanel
          documents={reviewDocs}
          selectedDocId={selectedReviewDocId}
          setSelectedDocId={setSelectedReviewDocId}
          qualityReport={qualityReport.data}
          onReview={review}
        />
      </div>

      <CompanyEvidencePanel
        profiles={companyProfiles.data ?? []}
        selectedCompanyId={selectedCompanyId}
        setSelectedCompanyId={setSelectedCompanyId}
        detail={companyDetail.data}
      />
    </div>
  );
}

function SourceBuilder({
  knowledgeBases,
  selectedKbId,
  setSelectedKbId,
  onError,
  onNotice,
}: {
  knowledgeBases: KnowledgeBase[];
  selectedKbId: string;
  setSelectedKbId: (value: string) => void;
  onError: (value: string) => void;
  onNotice: (value: string) => void;
}) {
  const queryClient = useQueryClient();
  const [sourceType, setSourceType] = React.useState<"files" | "web" | "mcp">("files");
  const [files, setFiles] = React.useState<File[]>([]);
  const [tags, setTags] = React.useState("default");
  const [confidentiality, setConfidentiality] = React.useState<Confidentiality>("Internal");
  const [connectorName, setConnectorName] = React.useState("");
  const [seedUrls, setSeedUrls] = React.useState("");
  const [allowlist, setAllowlist] = React.useState("");
  const [companyName, setCompanyName] = React.useState("");
  const [mcpConfig, setMcpConfig] = React.useState(DEFAULT_MCP_CONFIG);
  const [isBusy, setIsBusy] = React.useState(false);

  function addFiles(nextFiles: File[]) {
    setFiles((current) => {
      const seen = new Set(current.map(fileKey));
      const merged = [...current];
      for (const file of nextFiles) {
        const key = fileKey(file);
        if (!seen.has(key)) {
          seen.add(key);
          merged.push(file);
        }
      }
      return merged;
    });
  }

  async function uploadAndIndex() {
    if (!selectedKbId || !files.length) return;
    onError("");
    onNotice("");
    setIsBusy(true);
    try {
      const uploaded: DocumentRecord[] = [];
      for (const file of files) {
        uploaded.push(
          await uploadDocument(file, {
            knowledge_base_id: selectedKbId,
            tags: splitList(tags),
            confidentiality,
          }),
        );
      }
      const run = await createPipelineRun({
        knowledge_base_id: selectedKbId,
        document_ids: uploaded.map((doc) => doc.id),
        retrieval_index_config: { source: "data_hub_upload", reindex_strategy: "full_replace_chunks_and_vectors" },
      });
      setFiles([]);
      onNotice(`Uploaded ${uploaded.length} file(s). RAG pipeline queued with ${run.total_count} document(s).`);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["pipeline-runs"] });
      queryClient.invalidateQueries({ queryKey: ["workspace-summary"] });
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not upload files.");
    } finally {
      setIsBusy(false);
    }
  }

  async function saveConnector(syncAfterCreate: boolean) {
    onError("");
    onNotice("");
    setIsBusy(true);
    try {
      const kind = sourceType === "web" ? "web" : "mcp";
      const parsedMcpConfig = kind === "mcp" ? parseMcpConfig(mcpConfig) : {};
      const config =
        kind === "web"
          ? {
              seed_urls: splitList(seedUrls),
              allowlist_domains: splitList(allowlist),
              company_name: companyName || undefined,
              max_depth: 1,
              tags: splitList(tags),
            }
          : {
              ...parsedMcpConfig,
              transport: inferMcpTransport(parsedMcpConfig, "stdio"),
              disabled_tool_names: [],
            };
      const connection = await api<ConnectorConnection>("/connectors", {
        method: "POST",
        body: JSON.stringify({
          kind,
          scope: "organization",
          name: connectorName || (kind === "web" ? "Company website" : mcpServerName(config) ?? "MCP tools"),
          base_url: kind === "mcp" ? mcpBaseUrl(config) || undefined : undefined,
          is_enabled: true,
          config,
        }),
      });
      if (syncAfterCreate && selectedKbId) {
        await api(`/connectors/${connection.id}/sync`, {
          method: "POST",
          body: JSON.stringify({
            knowledge_base_id: selectedKbId,
            retrieval_index_config: { source: "data_hub_connector_sync", reindex_strategy: "connector_incremental_then_index" },
            share_with_organization: true,
            options: { company_name: companyName || undefined },
          }),
        });
      }
      setConnectorName("");
      setSeedUrls("");
      setAllowlist("");
      onNotice(syncAfterCreate ? "Source saved and sync queued." : "Connector saved.");
      queryClient.invalidateQueries({ queryKey: ["connectors"] });
      queryClient.invalidateQueries({ queryKey: ["workspace-summary"] });
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not save source.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <Panel className="p-5">
      <div className="flex items-center gap-2">
        <Database className="h-5 w-5 text-emerald-700" aria-hidden />
        <h3 className="font-semibold text-zinc-950">Add source</h3>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        {[
          { id: "files", label: "Files", icon: UploadCloud },
          { id: "web", label: "Web link", icon: Globe },
          { id: "mcp", label: "MCP", icon: Plug },
        ].map((option) => {
          const Icon = option.icon;
          return (
            <button
              key={option.id}
              className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium ${
                sourceType === option.id ? "border-emerald-300 bg-emerald-50 text-emerald-900" : "border-zinc-200"
              }`}
              onClick={() => setSourceType(option.id as "files" | "web" | "mcp")}
            >
              <Icon className="h-4 w-4" aria-hidden />
              {option.label}
            </button>
          );
        })}
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="space-y-2">
          <Label>Knowledge base</Label>
          <Select value={selectedKbId} onChange={(event) => setSelectedKbId(event.target.value)}>
            <option value="">Select knowledge base</option>
            {knowledgeBases.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Confidentiality</Label>
          <Select value={confidentiality} onChange={(event) => setConfidentiality(event.target.value as Confidentiality)}>
            {["Public", "Internal", "Confidential", "Restricted"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Tags</Label>
          <Input value={tags} onChange={(event) => setTags(event.target.value)} />
        </div>
      </div>
      {sourceType === "files" ? (
        <div className="mt-4 space-y-3">
          <label className="flex min-h-36 cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-zinc-300 bg-zinc-50 text-center hover:bg-white">
            <UploadCloud className="h-8 w-8 text-zinc-400" aria-hidden />
            <span className="mt-2 text-sm font-medium text-zinc-950">Select files</span>
            <input
              className="sr-only"
              type="file"
              multiple
              onChange={(event) => {
                addFiles(Array.from(event.target.files ?? []));
                event.currentTarget.value = "";
              }}
            />
          </label>
          {files.map((file) => (
            <div key={fileKey(file)} className="flex items-center justify-between rounded-md border border-zinc-200 px-3 py-2">
              <span className="text-sm font-medium text-zinc-800">{file.name}</span>
              <div className="flex items-center gap-2">
                <Badge>{formatBytes(file.size)}</Badge>
                <Button variant="ghost" size="icon" onClick={() => setFiles((current) => current.filter((item) => fileKey(item) !== fileKey(file)))}>
                  <X className="h-4 w-4" aria-hidden />
                </Button>
              </div>
            </div>
          ))}
          <Button disabled={!selectedKbId || !files.length || isBusy} onClick={uploadAndIndex}>
            <Play className="h-4 w-4" aria-hidden />
            Upload files and start RAG pipeline
          </Button>
        </div>
      ) : null}
      {sourceType === "web" ? (
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <Label>Source name</Label>
            <Input value={connectorName} onChange={(event) => setConnectorName(event.target.value)} placeholder="Website scrape" />
          </div>
          <div className="space-y-2">
            <Label>Company profile name</Label>
            <Input value={companyName} onChange={(event) => setCompanyName(event.target.value)} />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>Web links</Label>
            <Input value={seedUrls} onChange={(event) => setSeedUrls(event.target.value)} placeholder="https://example.com, https://example.com/docs" />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>Allowed domains</Label>
            <Input value={allowlist} onChange={(event) => setAllowlist(event.target.value)} placeholder="example.com" />
          </div>
          <Button disabled={!seedUrls || !selectedKbId || isBusy} onClick={() => saveConnector(true)}>
            <Save className="h-4 w-4" aria-hidden />
            Scrape web links and start RAG pipeline
          </Button>
        </div>
      ) : null}
      {sourceType === "mcp" ? (
        <div className="mt-4 space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Connector name</Label>
              <Input value={connectorName} onChange={(event) => setConnectorName(event.target.value)} />
            </div>
          </div>
          <div className="space-y-2">
            <Label>Cursor MCP JSON</Label>
            <Textarea className="min-h-56 font-mono text-xs" value={mcpConfig} onChange={(event) => setMcpConfig(event.target.value)} spellCheck={false} />
          </div>
          <Button disabled={isBusy} onClick={() => saveConnector(false)}>
            <Save className="h-4 w-4" aria-hidden />
            Save live connector
          </Button>
        </div>
      ) : null}
    </Panel>
  );
}

function SourcesPanel({
  connectors,
  activeConnectionId,
  setActiveConnectionId,
  onTest,
  onSync,
  onToggle,
  onToggleTool,
}: {
  connectors: ConnectorConnection[];
  activeConnectionId: string;
  setActiveConnectionId: (id: string) => void;
  onTest: (connection: ConnectorConnection) => void;
  onSync: (connection: ConnectorConnection) => void;
  onToggle: (connection: ConnectorConnection) => void;
  onToggleTool: (connection: ConnectorConnection, toolName: string) => void;
}) {
  return (
    <Panel className="p-5">
      <div className="flex items-center gap-2">
        <Plug className="h-5 w-5 text-sky-700" aria-hidden />
        <h3 className="font-semibold text-zinc-950">Sources</h3>
      </div>
      <div className="mt-4 divide-y divide-zinc-100">
        {connectors.map((connection) => (
          <div key={connection.id} className="py-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-medium text-zinc-950">{connection.name}</p>
                <p className="text-sm text-zinc-500">
                  {connection.kind} / {connection.scope} / {connection.indexed_item_count} indexed item(s)
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <StatusBadge status={connection.status} />
                  {connection.is_enabled ? <Badge tone="green">Enabled</Badge> : <Badge>Paused</Badge>}
                  {connection.live_tools_supported ? <Badge tone="blue">Live tools</Badge> : null}
                  {connection.web_search_supported ? <Badge tone="amber">Web mode</Badge> : null}
                </div>
                {connection.kind === "mcp" ? <SourceToolToggles connection={connection} onToggleTool={onToggleTool} /> : null}
              </div>
              <Button variant="ghost" size="icon" onClick={() => setActiveConnectionId(activeConnectionId === connection.id ? "" : connection.id)}>
                <History className="h-4 w-4" aria-hidden />
              </Button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => onTest(connection)}>
                <RotateCw className="h-4 w-4" aria-hidden />
                Test
              </Button>
              <Button variant="secondary" onClick={() => onToggle(connection)}>
                {connection.is_enabled ? "Pause" : "Enable"}
              </Button>
              {connection.sync_supported ? (
                <Button variant="secondary" onClick={() => onSync(connection)}>
                  <Play className="h-4 w-4" aria-hidden />
                  Sync
                </Button>
              ) : null}
            </div>
          </div>
        ))}
        {!connectors.length ? <EmptyState icon={Plug} title="No sources connected" body="Add files, a website, or an MCP connector to make company data queryable." /> : null}
      </div>
    </Panel>
  );
}

function TelegramSourcePanel({
  knowledgeBases,
  selectedKbId,
  profiles,
  onError,
  onNotice,
}: {
  knowledgeBases: KnowledgeBase[];
  selectedKbId: string;
  profiles?: Awaited<ReturnType<typeof listProfiles>>;
  onError: (value: string) => void;
  onNotice: (value: string) => void;
}) {
  const queryClient = useQueryClient();
  const integration = useQuery({ queryKey: ["telegram-integration"], queryFn: getTelegramIntegration });
  const allowedUsers = useQuery({ queryKey: ["telegram-allowed-users"], queryFn: listTelegramAllowedUsers });
  const messages = useQuery({ queryKey: ["telegram-messages"], queryFn: listTelegramMessages, refetchInterval: 5000 });
  const members = useQuery({ queryKey: ["members"], queryFn: listMembers });
  const [botToken, setBotToken] = React.useState("");
  const [botUsername, setBotUsername] = React.useState("");
  const [defaultKbId, setDefaultKbId] = React.useState("");
  const [chatProfileId, setChatProfileId] = React.useState("");
  const [enabled, setEnabled] = React.useState(false);
  const [autoText, setAutoText] = React.useState(true);
  const [autoDocs, setAutoDocs] = React.useState(true);
  const [autoVoice, setAutoVoice] = React.useState(true);
  const [userDraft, setUserDraft] = React.useState({
    username: "",
    telegram_user_id: "",
    phone_number: "",
    display_name: "",
    user_id: "",
    can_ingest: true,
    can_query: true,
  });

  React.useEffect(() => {
    const data = integration.data;
    if (!data) return;
    setBotUsername(data.bot_username ?? "");
    setDefaultKbId(data.default_knowledge_base_id ?? selectedKbId);
    setChatProfileId(data.default_chat_model_profile_id ?? "");
    setEnabled(data.is_enabled);
    setAutoText(data.auto_ingest_text);
    setAutoDocs(data.auto_ingest_documents);
    setAutoVoice(data.auto_ingest_voice);
  }, [integration.data, selectedKbId]);

  async function saveIntegration() {
    onError("");
    onNotice("");
    try {
      await api<TelegramIntegration>("/integrations/telegram", {
        method: "PATCH",
        body: JSON.stringify({
          bot_token: botToken || undefined,
          bot_username: botUsername || undefined,
          default_knowledge_base_id: defaultKbId || selectedKbId || undefined,
          default_chat_model_profile_id: chatProfileId || undefined,
          auto_ingest_text: autoText,
          auto_ingest_documents: autoDocs,
          auto_ingest_voice: autoVoice,
          is_enabled: enabled,
        }),
      });
      setBotToken("");
      onNotice("Telegram bot settings saved.");
      queryClient.invalidateQueries({ queryKey: ["telegram-integration"] });
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not save Telegram settings.");
    }
  }

  async function testBot() {
    onError("");
    onNotice("");
    try {
      const result = await api<{ bot: { username?: string } }>("/integrations/telegram/test", { method: "POST" });
      onNotice(`Connected to @${result.bot.username ?? "telegram bot"}.`);
      queryClient.invalidateQueries({ queryKey: ["telegram-integration"] });
    } catch (err) {
      onError(err instanceof Error ? err.message : "Telegram bot test failed.");
    }
  }

  async function registerWebhook() {
    onError("");
    onNotice("");
    try {
      await api("/integrations/telegram/register-webhook", { method: "POST" });
      onNotice("Telegram webhook registered.");
      queryClient.invalidateQueries({ queryKey: ["telegram-integration"] });
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not register webhook.");
    }
  }

  async function addAllowedUser() {
    onError("");
    try {
      await api<TelegramAllowedUser>("/integrations/telegram/allowed-users", {
        method: "POST",
        body: JSON.stringify({
          username: userDraft.username || undefined,
          telegram_user_id: userDraft.telegram_user_id ? Number(userDraft.telegram_user_id) : undefined,
          phone_number: userDraft.phone_number || undefined,
          display_name: userDraft.display_name || undefined,
          user_id: userDraft.user_id || undefined,
          can_ingest: userDraft.can_ingest,
          can_query: userDraft.can_query,
        }),
      });
      setUserDraft({
        username: "",
        telegram_user_id: "",
        phone_number: "",
        display_name: "",
        user_id: "",
        can_ingest: true,
        can_query: true,
      });
      queryClient.invalidateQueries({ queryKey: ["telegram-allowed-users"] });
      onNotice("Telegram user allowed.");
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not add Telegram user.");
    }
  }

  async function removeAllowedUser(user: TelegramAllowedUser) {
    await api(`/integrations/telegram/allowed-users/${user.id}`, { method: "DELETE" });
    queryClient.invalidateQueries({ queryKey: ["telegram-allowed-users"] });
  }

  return (
    <Panel className="p-5">
      <div className="flex items-center gap-2">
        <Bot className="h-5 w-5 text-sky-700" aria-hidden />
        <h3 className="font-semibold text-zinc-950">Telegram source</h3>
        {integration.data?.is_enabled ? <Badge tone="green">Enabled</Badge> : <Badge>Paused</Badge>}
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Bot token</Label>
              <Input type="password" value={botToken} onChange={(event) => setBotToken(event.target.value)} placeholder={integration.data?.masked_bot_token ?? ""} />
            </div>
            <div className="space-y-2">
              <Label>Bot username</Label>
              <Input value={botUsername} onChange={(event) => setBotUsername(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Default knowledge base</Label>
              <Select value={defaultKbId || selectedKbId} onChange={(event) => setDefaultKbId(event.target.value)}>
                <option value="">Select knowledge base</option>
                {knowledgeBases.map((kb) => (
                  <option key={kb.id} value={kb.id}>
                    {kb.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Answer model</Label>
              <Select value={chatProfileId} onChange={(event) => setChatProfileId(event.target.value)}>
                <option value="">Local fallback</option>
                {(profiles?.chat_profiles ?? []).map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.provider} / {profile.model_name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-3 rounded-md bg-zinc-50 p-3">
              <Toggle label="Enabled" checked={enabled} onChange={setEnabled} />
              <Toggle label="Ingest text" checked={autoText} onChange={setAutoText} />
              <Toggle label="Ingest documents" checked={autoDocs} onChange={setAutoDocs} />
              <Toggle label="Ingest voice" checked={autoVoice} onChange={setAutoVoice} />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={saveIntegration}>
              <Save className="h-4 w-4" aria-hidden />
              Save Telegram
            </Button>
            <Button variant="secondary" onClick={testBot}>
              <RotateCw className="h-4 w-4" aria-hidden />
              Test bot
            </Button>
            <Button variant="secondary" onClick={registerWebhook}>
              <Plug className="h-4 w-4" aria-hidden />
              Register webhook
            </Button>
          </div>
          {integration.data ? (
            <div className="rounded-md bg-zinc-50 p-3 text-sm text-zinc-600">
              <p className="break-all">{integration.data.webhook_url}</p>
              <p className="mt-1 break-all">Secret: {integration.data.webhook_secret_token}</p>
            </div>
          ) : null}
        </div>
        <div className="space-y-4">
          <div className="rounded-md border border-zinc-200 p-4">
            <h4 className="font-semibold text-zinc-950">Allowed users</h4>
            <div className="mt-3 grid gap-2">
              <Input value={userDraft.username} onChange={(event) => setUserDraft({ ...userDraft, username: event.target.value })} placeholder="@username" />
              <Input value={userDraft.telegram_user_id} onChange={(event) => setUserDraft({ ...userDraft, telegram_user_id: event.target.value })} placeholder="Telegram user ID" />
              <Input value={userDraft.display_name} onChange={(event) => setUserDraft({ ...userDraft, display_name: event.target.value })} placeholder="Display name" />
              <Select value={userDraft.user_id} onChange={(event) => setUserDraft({ ...userDraft, user_id: event.target.value })}>
                <option value="">Link RAG account for Ask</option>
                {(members.data ?? []).map((member) => (
                  <option key={member.id} value={member.user_id}>
                    {member.email}
                  </option>
                ))}
              </Select>
              <div className="flex flex-wrap gap-3">
                <Toggle label="Can ingest" checked={userDraft.can_ingest} onChange={(value) => setUserDraft({ ...userDraft, can_ingest: value })} />
                <Toggle label="Can ask" checked={userDraft.can_query} onChange={(value) => setUserDraft({ ...userDraft, can_query: value })} />
              </div>
              <Button disabled={!userDraft.username && !userDraft.telegram_user_id && !userDraft.phone_number} onClick={addAllowedUser}>
                <Check className="h-4 w-4" aria-hidden />
                Allow user
              </Button>
            </div>
            <div className="mt-4 divide-y divide-zinc-100">
              {(allowedUsers.data ?? []).map((user) => (
                <div key={user.id} className="flex items-center justify-between gap-3 py-2">
                  <div>
                    <p className="text-sm font-medium text-zinc-950">{user.display_name || user.username || user.telegram_user_id}</p>
                    <div className="mt-1 flex gap-2">
                      {user.can_ingest ? <Badge tone="green">Ingest</Badge> : null}
                      {user.can_query ? <Badge tone="blue">Ask</Badge> : null}
                      {user.user_id ? <Badge>Linked</Badge> : null}
                    </div>
                  </div>
                  <Button variant="ghost" size="icon" onClick={() => removeAllowedUser(user)}>
                    <X className="h-4 w-4" aria-hidden />
                  </Button>
                </div>
              ))}
            </div>
          </div>
          <TelegramMessages messages={messages.data ?? []} />
        </div>
      </div>
    </Panel>
  );
}

function TelegramMessages({ messages }: { messages: TelegramMessageLog[] }) {
  return (
    <div className="rounded-md border border-zinc-200 p-4">
      <h4 className="font-semibold text-zinc-950">Recent Telegram messages</h4>
      <div className="mt-3 max-h-80 divide-y divide-zinc-100 overflow-auto">
        {messages.map((message) => (
          <div key={message.id} className="py-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-zinc-950">
                  {message.mode} / {message.source_type}
                </p>
                <p className="text-xs text-zinc-500">
                  chat {message.telegram_chat_id} / message {message.telegram_message_id}
                </p>
              </div>
              <StatusBadge status={message.status} />
            </div>
            {message.error ? <p className="mt-2 text-sm text-rose-700">{message.error}</p> : null}
            <p className="mt-1 text-xs text-zinc-500">{shortDate(message.created_at)}</p>
          </div>
        ))}
        {!messages.length ? <p className="text-sm text-zinc-500">No Telegram messages received yet.</p> : null}
      </div>
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm text-zinc-700">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      {label}
    </label>
  );
}

function ConnectorDetailPanel({ connection, runs, items }: { connection: ConnectorConnection; runs: ConnectorRun[]; items: ConnectorItem[] }) {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel className="p-5">
        <h3 className="font-semibold text-zinc-950">{connection.name} sync history</h3>
        <div className="mt-4 divide-y divide-zinc-100">
          {runs.map((run) => (
            <div key={run.id} className="grid gap-2 py-3 text-sm md:grid-cols-[140px_1fr_100px] md:items-center">
              <span className="text-zinc-500">{shortDate(run.created_at)}</span>
              <StatusBadge status={run.status} />
              <span className="text-zinc-600">
                {run.processed_items}/{run.total_items}
              </span>
              {run.error ? <p className="md:col-span-3 text-rose-700">{run.error}</p> : null}
            </div>
          ))}
          {!runs.length ? <p className="text-sm text-zinc-500">No sync runs yet.</p> : null}
        </div>
      </Panel>
      <Panel className="p-5">
        <h3 className="font-semibold text-zinc-950">Indexed connector items</h3>
        <div className="mt-4 max-h-80 divide-y divide-zinc-100 overflow-auto">
          {items.map((item) => (
            <div key={item.id} className="py-3">
              <p className="text-sm font-medium text-zinc-950">{item.title}</p>
              <div className="mt-1 flex flex-wrap gap-2 text-xs text-zinc-500">
                <StatusBadge status={item.status} />
                {item.source_url ? <span className="break-all">{item.source_url}</span> : null}
              </div>
            </div>
          ))}
          {!items.length ? <p className="text-sm text-zinc-500">No connector items have been indexed yet.</p> : null}
        </div>
      </Panel>
    </div>
  );
}

function KnowledgePanel({
  docs,
  kbs,
  selectedKbId,
  setSelectedKbId,
}: {
  docs: DocumentRecord[];
  kbs: KnowledgeBase[];
  selectedKbId: string;
  setSelectedKbId: (value: string) => void;
}) {
  const queryClient = useQueryClient();
  const [selectedIds, setSelectedIds] = React.useState<string[]>([]);
  const [previewDocId, setPreviewDocId] = React.useState("");
  const [previewKind, setPreviewKind] = React.useState("cleaned");
  const [editingDocId, setEditingDocId] = React.useState("");
  const [editName, setEditName] = React.useState("");
  const [editTags, setEditTags] = React.useState("");
  const [editBusinessUnit, setEditBusinessUnit] = React.useState("");
  const [editConfidentiality, setEditConfidentiality] = React.useState<Confidentiality>("Internal");
  const [busyAction, setBusyAction] = React.useState("");
  const [panelError, setPanelError] = React.useState("");
  const [panelNotice, setPanelNotice] = React.useState("");

  React.useEffect(() => {
    setSelectedIds((current) => current.filter((id) => docs.some((doc) => doc.id === id)));
  }, [docs]);

  const preview = useQuery({
    queryKey: ["document-preview", previewDocId, previewKind],
    enabled: Boolean(previewDocId),
    queryFn: () => previewDocument(previewDocId, previewKind),
  });
  const previewDoc = docs.find((doc) => doc.id === previewDocId);
  const editingDoc = docs.find((doc) => doc.id === editingDocId);
  const selectedDocs = docs.filter((doc) => selectedIds.includes(doc.id));
  const allVisibleSelected = docs.length > 0 && docs.every((doc) => selectedIds.includes(doc.id));

  function toggleSelected(id: string) {
    setSelectedIds((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  function editDocument(doc: DocumentRecord) {
    setEditingDocId(doc.id);
    setEditName(doc.name);
    setEditTags(doc.tags.join(", "));
    setEditBusinessUnit(doc.business_unit ?? "");
    setEditConfidentiality(doc.confidentiality);
  }

  async function queueReindex(targetDocs: DocumentRecord[]) {
    setPanelError("");
    setPanelNotice("");
    if (!targetDocs.length) {
      setPanelError("Select at least one document to reindex.");
      return;
    }
    const targetKbId = selectedKbId || targetDocs[0]?.knowledge_base_id;
    if (!targetKbId || targetDocs.some((doc) => doc.knowledge_base_id !== targetKbId)) {
      setPanelError("Reindex documents from one knowledge base at a time.");
      return;
    }
    setBusyAction("reindex");
    try {
      const run = await createPipelineRun({
        knowledge_base_id: targetKbId,
        document_ids: targetDocs.map((doc) => doc.id),
        retrieval_index_config: { source: "data_hub_reindex", reindex_strategy: "full_replace_chunks_and_vectors" },
      });
      setPanelNotice(`RAG pipeline queued for ${run.total_count} document(s).`);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["pipeline-runs"] });
      queryClient.invalidateQueries({ queryKey: ["workspace-summary"] });
    } catch (err) {
      setPanelError(err instanceof Error ? err.message : "Could not start the RAG pipeline.");
    } finally {
      setBusyAction("");
    }
  }

  async function saveMetadata(reindex: boolean) {
    if (!editingDoc) return;
    setPanelError("");
    setPanelNotice("");
    setBusyAction("metadata");
    try {
      const updated = await updateDocument(editingDoc.id, {
        name: editName,
        tags: splitList(editTags),
        business_unit: editBusinessUnit,
        confidentiality: editConfidentiality,
      });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      if (reindex) {
        await queueReindex([updated]);
      } else {
        setPanelNotice("Document metadata saved.");
      }
    } catch (err) {
      setPanelError(err instanceof Error ? err.message : "Could not save document metadata.");
    } finally {
      setBusyAction("");
    }
  }

  async function removeDocument(doc: DocumentRecord) {
    if (!window.confirm(`Delete ${doc.name}? It will be removed from Ask results.`)) return;
    setPanelError("");
    setPanelNotice("");
    setBusyAction(`delete-${doc.id}`);
    try {
      await deleteDocument(doc.id);
      setSelectedIds((current) => current.filter((id) => id !== doc.id));
      if (previewDocId === doc.id) setPreviewDocId("");
      if (editingDocId === doc.id) setEditingDocId("");
      setPanelNotice("Document deleted.");
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["workspace-summary"] });
    } catch (err) {
      setPanelError(err instanceof Error ? err.message : "Could not delete document.");
    } finally {
      setBusyAction("");
    }
  }

  async function replaceFile(doc: DocumentRecord, file?: File) {
    if (!file) return;
    setPanelError("");
    setPanelNotice("");
    setBusyAction(`replace-${doc.id}`);
    try {
      const updated = await replaceDocumentFile(doc.id, file);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      await queueReindex([updated]);
      setPanelNotice(`Replaced ${doc.name} and queued reindexing.`);
    } catch (err) {
      setPanelError(err instanceof Error ? err.message : "Could not replace document.");
    } finally {
      setBusyAction("");
    }
  }

  return (
    <Panel className="overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3">
        <div>
          <h3 className="font-semibold text-zinc-950">Company data</h3>
          <p className="mt-1 text-xs text-zinc-500">{selectedIds.length} selected for reindexing</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button variant="secondary" disabled={!selectedIds.length || busyAction === "reindex"} onClick={() => queueReindex(selectedDocs)}>
            <RefreshCw className="h-4 w-4" aria-hidden />
            Start RAG pipeline
          </Button>
          <Select className="max-w-64" value={selectedKbId} onChange={(event) => setSelectedKbId(event.target.value)}>
            <option value="">All knowledge bases</option>
            {kbs.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name}
              </option>
            ))}
          </Select>
        </div>
      </div>
      {panelError ? <div className="border-b border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-800">{panelError}</div> : null}
      {panelNotice ? <div className="border-b border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-800">{panelNotice}</div> : null}
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-zinc-200 text-sm">
          <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
            <tr>
              <th className="w-10 px-4 py-3">
                <input
                  type="checkbox"
                  checked={allVisibleSelected}
                  onChange={(event) => setSelectedIds(event.target.checked ? docs.map((doc) => doc.id) : [])}
                />
              </th>
              <th className="px-4 py-3">Document</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Security</th>
              <th className="px-4 py-3">Updated</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 bg-white">
            {docs.map((doc) => (
              <tr key={doc.id}>
                <td className="px-4 py-3">
                  <input type="checkbox" checked={selectedIds.includes(doc.id)} onChange={() => toggleSelected(doc.id)} />
                </td>
                <td className="px-4 py-3">
                  <p className="font-medium text-zinc-950">{doc.name}</p>
                  <p className="text-xs text-zinc-500">
                    v{doc.version_number} / {formatBytes(doc.file_size)} / {doc.source_url ?? doc.original_filename}
                  </p>
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={doc.processing_status} />
                </td>
                <td className="px-4 py-3">{doc.confidentiality}</td>
                <td className="px-4 py-3 text-zinc-600">{shortDate(doc.updated_at)}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    <Button variant="ghost" size="icon" title="Preview" onClick={() => setPreviewDocId(doc.id)}>
                      <Eye className="h-4 w-4" aria-hidden />
                    </Button>
                    <Button variant="ghost" size="icon" title="Edit metadata" onClick={() => editDocument(doc)}>
                      <Pencil className="h-4 w-4" aria-hidden />
                    </Button>
                    <label
                      className={`inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-md text-zinc-700 hover:bg-zinc-100 ${
                        busyAction === `replace-${doc.id}` ? "opacity-50" : ""
                      }`}
                      title="Replace file"
                    >
                      <FileUp className="h-4 w-4" aria-hidden />
                      <input
                        className="sr-only"
                        type="file"
                        onChange={(event) => {
                          void replaceFile(doc, event.target.files?.[0]);
                          event.currentTarget.value = "";
                        }}
                      />
                    </label>
                    <Button variant="ghost" size="icon" title="Reindex" onClick={() => queueReindex([doc])}>
                      <RefreshCw className="h-4 w-4" aria-hidden />
                    </Button>
                    <Button variant="ghost" size="icon" title="Delete" onClick={() => removeDocument(doc)}>
                      <Trash2 className="h-4 w-4" aria-hidden />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!docs.length ? <EmptyState icon={FileText} title="No documents yet" body="Add a source to create indexed company data." /> : null}
      {(previewDoc || editingDoc) && docs.length ? (
        <div className="grid gap-4 border-t border-zinc-200 bg-white p-4 xl:grid-cols-2">
          {previewDoc ? (
            <div className="rounded-md border border-zinc-200 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h4 className="font-semibold text-zinc-950">{previewDoc.name}</h4>
                  <p className="mt-1 text-xs text-zinc-500">Preview derived content from the latest pipeline run.</p>
                </div>
                <Select className="w-36" value={previewKind} onChange={(event) => setPreviewKind(event.target.value)}>
                  <option value="cleaned">Cleaned</option>
                  <option value="redacted">Redacted</option>
                  <option value="extracted">Extracted</option>
                  <option value="manual_edit">Manual edit</option>
                </Select>
              </div>
              <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap rounded-md bg-zinc-950 p-3 text-xs leading-5 text-zinc-100">
                {preview.isLoading ? "Loading preview..." : preview.data?.text || "No derived preview yet. Start the RAG pipeline to extract and clean this file."}
              </pre>
            </div>
          ) : null}
          {editingDoc ? (
            <div className="rounded-md border border-zinc-200 p-4">
              <h4 className="font-semibold text-zinc-950">Edit document</h4>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="space-y-2 md:col-span-2">
                  <Label>Name</Label>
                  <Input value={editName} onChange={(event) => setEditName(event.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Tags</Label>
                  <Input value={editTags} onChange={(event) => setEditTags(event.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Business unit</Label>
                  <Input value={editBusinessUnit} onChange={(event) => setEditBusinessUnit(event.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Confidentiality</Label>
                  <Select value={editConfidentiality} onChange={(event) => setEditConfidentiality(event.target.value as Confidentiality)}>
                    {["Public", "Internal", "Confidential", "Restricted"].map((value) => (
                      <option key={value}>{value}</option>
                    ))}
                  </Select>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button variant="secondary" disabled={busyAction === "metadata"} onClick={() => saveMetadata(false)}>
                  <Save className="h-4 w-4" aria-hidden />
                  Save metadata
                </Button>
                <Button disabled={busyAction === "metadata" || busyAction === "reindex"} onClick={() => saveMetadata(true)}>
                  <RefreshCw className="h-4 w-4" aria-hidden />
                  Save and reindex
                </Button>
                <Button variant="ghost" onClick={() => setEditingDocId("")}>
                  <X className="h-4 w-4" aria-hidden />
                  Close
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </Panel>
  );
}

function ReviewPanel({
  documents,
  selectedDocId,
  setSelectedDocId,
  qualityReport,
  onReview,
}: {
  documents: DocumentRecord[];
  selectedDocId: string;
  setSelectedDocId: (value: string) => void;
  qualityReport?: { summary?: string | null; severity: string; requires_review: boolean; issues: Array<Record<string, unknown>> };
  onReview: (doc: DocumentRecord, action: "continue_unchanged" | "exclude_document") => void;
}) {
  const selectedDoc = documents.find((doc) => doc.id === selectedDocId);
  return (
    <Panel className="p-5">
      <div className="flex items-center gap-2">
        <RefreshCw className="h-5 w-5 text-amber-700" aria-hidden />
        <h3 className="font-semibold text-zinc-950">Review queue</h3>
      </div>
      <div className="mt-4 space-y-3">
        {documents.map((doc) => (
          <div key={doc.id} className="rounded-md border border-zinc-200 p-3">
            <button className="w-full text-left" onClick={() => setSelectedDocId(selectedDocId === doc.id ? "" : doc.id)}>
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-medium text-zinc-950">{doc.name}</span>
                <StatusBadge status={doc.processing_status} />
              </div>
            </button>
            {selectedDoc?.id === doc.id ? (
              <div className="mt-3 space-y-3 border-t border-zinc-100 pt-3">
                <p className="text-sm text-zinc-600">{qualityReport?.summary ?? "No quality report yet."}</p>
                <div className="flex flex-wrap gap-2">
                  <Badge tone={qualityReport?.requires_review ? "amber" : "green"}>{qualityReport?.severity ?? "pending"}</Badge>
                  <Badge>{qualityReport?.issues.length ?? 0} issue(s)</Badge>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button variant="secondary" onClick={() => onReview(doc, "continue_unchanged")}>
                    <Check className="h-4 w-4" aria-hidden />
                    Continue
                  </Button>
                  <Button variant="danger" onClick={() => onReview(doc, "exclude_document")}>
                    <X className="h-4 w-4" aria-hidden />
                    Exclude
                  </Button>
                </div>
              </div>
            ) : null}
          </div>
        ))}
        {!documents.length ? <p className="text-sm text-zinc-500">No review items right now. Pipeline logs are in Activity.</p> : null}
      </div>
    </Panel>
  );
}

function CompanyEvidencePanel({
  profiles,
  selectedCompanyId,
  setSelectedCompanyId,
  detail,
}: {
  profiles: Array<{ id: string; name: string; description?: string | null; website_url?: string | null }>;
  selectedCompanyId: string;
  setSelectedCompanyId: (value: string) => void;
  detail?: { evidence?: Array<{ id: string; source_type: string; source_url?: string | null; excerpt?: string | null; field_name: string }> };
}) {
  return (
    <Panel className="p-5">
      <div className="flex items-center gap-2">
        <Building2 className="h-5 w-5 text-violet-700" aria-hidden />
        <h3 className="font-semibold text-zinc-950">Company evidence</h3>
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-[300px_1fr]">
        <div className="space-y-2">
          {profiles.map((profile) => (
            <button
              key={profile.id}
              className={`w-full rounded-md border px-3 py-2 text-left text-sm ${
                selectedCompanyId === profile.id ? "border-emerald-300 bg-emerald-50" : "border-zinc-200"
              }`}
              onClick={() => setSelectedCompanyId(profile.id)}
            >
              <span className="block font-medium text-zinc-950">{profile.name}</span>
              <span className="text-xs text-zinc-500">{profile.website_url ?? "Evidence profile"}</span>
            </button>
          ))}
          {!profiles.length ? <p className="text-sm text-zinc-500">Web/company sync has not created company evidence yet.</p> : null}
        </div>
        <div className="rounded-md border border-zinc-200 p-4">
          {(detail?.evidence ?? []).map((evidence) => (
            <div key={evidence.id} className="border-b border-zinc-100 py-3 first:pt-0 last:border-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="blue">{evidence.source_type}</Badge>
                <span className="text-sm font-medium text-zinc-950">{evidence.field_name}</span>
              </div>
              {evidence.source_url ? <p className="mt-1 break-all text-xs text-sky-700">{evidence.source_url}</p> : null}
              <p className="mt-2 text-sm leading-6 text-zinc-600">{evidence.excerpt ?? "No excerpt stored."}</p>
            </div>
          ))}
          {selectedCompanyId && !(detail?.evidence ?? []).length ? <p className="text-sm text-zinc-500">No evidence rows for this company yet.</p> : null}
          {!selectedCompanyId ? <p className="text-sm text-zinc-500">Select a company profile to inspect evidence.</p> : null}
        </div>
      </div>
    </Panel>
  );
}

function HubStat({ label, value, icon: Icon }: { label: string; value: number; icon: typeof Archive }) {
  return (
    <Panel className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-zinc-500">{label}</p>
          <p className="mt-2 text-2xl font-semibold text-zinc-950">{value}</p>
        </div>
        <span className="flex h-10 w-10 items-center justify-center rounded-md bg-sky-50 text-sky-700">
          <Icon className="h-5 w-5" aria-hidden />
        </span>
      </div>
    </Panel>
  );
}

interface McpToolSummary {
  name: string;
  description?: string;
}

function SourceToolToggles({
  connection,
  onToggleTool,
}: {
  connection: ConnectorConnection;
  onToggleTool: (connection: ConnectorConnection, toolName: string) => void;
}) {
  const tools = toolsForConnection(connection);
  if (!tools.length) return null;
  const disabled = stringList(connection.config.disabled_tool_names);
  return (
    <div className="mt-3 space-y-2 rounded-md border border-zinc-200 p-3">
      <p className="text-xs font-medium uppercase text-zinc-500">Detected tools</p>
      {tools.map((tool) => {
        const active = !disabled.includes(tool.name);
        return (
          <label key={tool.name} className="flex items-start justify-between gap-3 text-sm text-zinc-700">
            <span>
              <span className="block font-medium text-zinc-900">{tool.name}</span>
              {tool.description ? <span className="block text-xs text-zinc-500">{tool.description}</span> : null}
            </span>
            <input type="checkbox" checked={active} onChange={() => onToggleTool(connection, tool.name)} />
          </label>
        );
      })}
    </div>
  );
}

function toolsForConnection(connection: ConnectorConnection): McpToolSummary[] {
  const cached = connection.config.discovered_tools;
  if (!Array.isArray(cached)) return [];
  return cached
    .filter((tool): tool is Record<string, unknown> => Boolean(tool) && typeof tool === "object" && !Array.isArray(tool))
    .map((tool) => ({ name: String(tool.name ?? ""), description: String(tool.description ?? "") }))
    .filter((tool) => tool.name);
}

function stringList(value: unknown) {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function splitList(value: string) {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function fileKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function parseMcpConfig(value: string): Record<string, unknown> {
  const trimmed = value.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Cursor MCP JSON must be an object.");
  }
  return parsed as Record<string, unknown>;
}

function mcpServerName(config: Record<string, unknown>) {
  const selectedName = config.mcp_server_name ?? config.server_name;
  if (typeof selectedName === "string" && selectedName.trim()) return selectedName.trim();
  const servers = config.mcpServers;
  if (!servers || typeof servers !== "object" || Array.isArray(servers)) return null;
  for (const [name, value] of Object.entries(servers)) {
    if (value && typeof value === "object" && !Array.isArray(value) && (value as { disabled?: unknown }).disabled !== true) {
      return name;
    }
  }
  return null;
}

function inferMcpTransport(config: Record<string, unknown>, fallback: string) {
  const server = firstMcpServer(config);
  if (server && (String(server.type ?? "").toLowerCase() === "http" || typeof server.url === "string")) {
    return "streamable_http";
  }
  return fallback;
}

function mcpBaseUrl(config: Record<string, unknown>) {
  const server = firstMcpServer(config);
  return typeof server?.url === "string" ? server.url : null;
}

function firstMcpServer(config: Record<string, unknown>) {
  const servers = config.mcpServers;
  if (!servers || typeof servers !== "object" || Array.isArray(servers)) return null;
  const selectedName = config.mcp_server_name ?? config.server_name;
  if (typeof selectedName === "string") {
    const selected = (servers as Record<string, unknown>)[selectedName];
    return selected && typeof selected === "object" && !Array.isArray(selected) ? (selected as Record<string, unknown>) : null;
  }
  for (const value of Object.values(servers)) {
    if (value && typeof value === "object" && !Array.isArray(value) && (value as { disabled?: unknown }).disabled !== true) {
      return value as Record<string, unknown>;
    }
  }
  return null;
}
