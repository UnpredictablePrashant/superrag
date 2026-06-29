"use client";

import { EmptyState } from "@/components/empty-state";
import { ErrorBox } from "@/components/error-box";
import { StatusBadge } from "@/components/status-badge";
import {
  api,
  ConnectorConnection,
  ConnectorItem,
  ConnectorRun,
  getCompanyProfile,
  getDocumentQualityReport,
  getWorkspaceSummary,
  listCompanyProfiles,
  listConnectorItems,
  listConnectorRuns,
  listConnectors,
  listDocuments,
  listKnowledgeBases,
  listPipelineRuns,
  listProfiles,
  reviewDocument,
} from "@/lib/api";
import { formatBytes, shortDate } from "@/lib/format";
import type { Confidentiality, DocumentRecord, KnowledgeBase, PipelineRun } from "@rag-console/shared-types";
import { Badge, Button, Input, Label, Panel, Select, Textarea } from "@rag-console/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  Building2,
  Check,
  Database,
  FileText,
  Globe,
  History,
  Play,
  Plug,
  RefreshCw,
  RotateCw,
  Save,
  Search,
  UploadCloud,
  X,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

const DEFAULT_MCP_CONFIG = `{
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
  const runs = useQuery({ queryKey: ["pipeline-runs"], queryFn: listPipelineRuns, refetchInterval: 5000 });
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
      const result = await api<{ status: string; message?: string }>(`/connectors/${connection.id}/test`, { method: "POST" });
      setNotice(result.status === "ok" ? "Connector test passed." : result.message ?? "Connector test failed.");
      queryClient.invalidateQueries({ queryKey: ["connectors"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connector test failed.");
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
  const pipelineAttention = (runs.data ?? []).filter((run) =>
    ["FAILED", "AWAITING_REVIEW", "COMPLETED_WITH_WARNINGS"].includes(run.current_stage),
  );
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
          profiles={profiles.data}
          onError={setError}
          onNotice={setNotice}
        />
        <SourcesPanel
          connectors={connectors.data ?? []}
          activeConnectionId={activeConnectionId}
          setActiveConnectionId={setActiveConnectionId}
          onTest={testConnector}
          onSync={syncConnector}
        />
      </div>

      {activeConnection ? (
        <ConnectorDetailPanel connection={activeConnection} runs={connectorRuns.data ?? []} items={connectorItems.data ?? []} />
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[1fr_0.95fr]">
        <KnowledgePanel docs={allDocs} kbs={kbs.data ?? []} selectedKbId={selectedKbId} setSelectedKbId={setSelectedKbId} />
        <ReviewPanel
          documents={reviewDocs}
          pipelines={pipelineAttention}
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
  profiles,
  onError,
  onNotice,
}: {
  knowledgeBases: KnowledgeBase[];
  selectedKbId: string;
  setSelectedKbId: (value: string) => void;
  profiles?: Awaited<ReturnType<typeof listProfiles>>;
  onError: (value: string) => void;
  onNotice: (value: string) => void;
}) {
  const queryClient = useQueryClient();
  const [sourceType, setSourceType] = React.useState<"files" | "web" | "mcp">("files");
  const [files, setFiles] = React.useState<File[]>([]);
  const [tags, setTags] = React.useState("default");
  const [confidentiality, setConfidentiality] = React.useState<Confidentiality>("Internal");
  const [cleanupProfileId, setCleanupProfileId] = React.useState("");
  const [chunkingProfileId, setChunkingProfileId] = React.useState("");
  const [embeddingProfileId, setEmbeddingProfileId] = React.useState("");
  const [connectorName, setConnectorName] = React.useState("");
  const [seedUrls, setSeedUrls] = React.useState("");
  const [allowlist, setAllowlist] = React.useState("");
  const [companyName, setCompanyName] = React.useState("");
  const [mcpConfig, setMcpConfig] = React.useState(DEFAULT_MCP_CONFIG);
  const [enabledToolNames, setEnabledToolNames] = React.useState("");
  const [isBusy, setIsBusy] = React.useState(false);

  React.useEffect(() => {
    if (!cleanupProfileId && profiles?.cleanup_profiles[1]) setCleanupProfileId(profiles.cleanup_profiles[1].id);
    if (!chunkingProfileId && profiles?.chunking_profiles[0]) setChunkingProfileId(profiles.chunking_profiles[0].id);
    if (!embeddingProfileId && profiles?.embedding_profiles[0]) setEmbeddingProfileId(profiles.embedding_profiles[0].id);
  }, [cleanupProfileId, chunkingProfileId, embeddingProfileId, profiles]);

  async function uploadAndIndex() {
    if (!selectedKbId || !files.length) return;
    onError("");
    onNotice("");
    setIsBusy(true);
    try {
      const uploaded: DocumentRecord[] = [];
      for (const file of files) {
        const presign = await api<{
          document_id: string;
          upload_url: string;
          headers: Record<string, string>;
          multipart: boolean;
          upload_id?: string;
          part_urls?: Array<{ part_number: number; url: string }>;
        }>("/uploads/presign", {
          method: "POST",
          body: JSON.stringify({
            filename: file.name,
            content_type: file.type || "application/octet-stream",
            size_bytes: file.size,
            knowledge_base_id: selectedKbId,
            tags: splitList(tags),
            confidentiality,
          }),
        });
        if (presign.multipart && presign.part_urls?.length) {
          const parts = [];
          const partSize = Math.ceil(file.size / presign.part_urls.length);
          for (const part of presign.part_urls) {
            const start = (part.part_number - 1) * partSize;
            const end = Math.min(file.size, start + partSize);
            const response = await fetch(part.url, { method: "PUT", body: file.slice(start, end) });
            if (!response.ok) throw new Error(`Part ${part.part_number} upload failed.`);
            parts.push({ PartNumber: part.part_number, ETag: response.headers.get("ETag")?.replaceAll("\"", "") });
          }
          await api("/uploads/complete", {
            method: "POST",
            body: JSON.stringify({ document_id: presign.document_id, upload_id: presign.upload_id, parts }),
          });
        } else {
          const response = await fetch(presign.upload_url, { method: "PUT", body: file, headers: presign.headers });
          if (!response.ok) throw new Error(`Upload failed for ${file.name}.`);
          await api("/uploads/complete", { method: "POST", body: JSON.stringify({ document_id: presign.document_id }) });
        }
        uploaded.push(await api<DocumentRecord>(`/documents/${presign.document_id}`));
      }
      const run = await api<PipelineRun>("/pipeline-runs", {
        method: "POST",
        body: JSON.stringify({
          knowledge_base_id: selectedKbId,
          document_ids: uploaded.map((doc) => doc.id),
          cleanup_profile_id: cleanupProfileId || undefined,
          chunking_profile_id: chunkingProfileId || undefined,
          embedding_profile_id: embeddingProfileId || undefined,
          retrieval_index_config: { max_chunks: 8, rrf_constant: 60 },
        }),
      });
      setFiles([]);
      onNotice(`Uploaded ${uploaded.length} file(s). Pipeline ${run.current_stage} has started.`);
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
      const enabledTools = splitList(enabledToolNames);
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
              transport: "stdio",
              ...parseMcpConfig(mcpConfig),
              enabled_tool_names: enabledTools,
              tool_tags: Object.fromEntries(enabledTools.map((tool) => [tool, ["web_search", "knowledge_lookup"]])),
            };
      const connection = await api<ConnectorConnection>("/connectors", {
        method: "POST",
        body: JSON.stringify({
          kind,
          scope: "organization",
          name: connectorName || (kind === "web" ? "Company website" : mcpServerName(config) ?? "MCP tools"),
          is_enabled: true,
          config,
        }),
      });
      if (syncAfterCreate && selectedKbId) {
        await api(`/connectors/${connection.id}/sync`, {
          method: "POST",
          body: JSON.stringify({
            knowledge_base_id: selectedKbId,
            cleanup_profile_id: cleanupProfileId || undefined,
            chunking_profile_id: chunkingProfileId || undefined,
            embedding_profile_id: embeddingProfileId || undefined,
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
          { id: "web", label: "Website", icon: Globe },
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
        <ProfileSelect label="Cleanup" value={cleanupProfileId} onChange={setCleanupProfileId} options={profiles?.cleanup_profiles ?? []} />
        <ProfileSelect label="Chunking" value={chunkingProfileId} onChange={setChunkingProfileId} options={profiles?.chunking_profiles ?? []} />
        <ProfileSelect label="Embedding" value={embeddingProfileId} onChange={setEmbeddingProfileId} options={profiles?.embedding_profiles ?? []} />
      </div>
      {sourceType === "files" ? (
        <div className="mt-4 space-y-3">
          <label className="flex min-h-36 cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-zinc-300 bg-zinc-50 text-center hover:bg-white">
            <UploadCloud className="h-8 w-8 text-zinc-400" aria-hidden />
            <span className="mt-2 text-sm font-medium text-zinc-950">Select files</span>
            <input className="sr-only" type="file" multiple onChange={(event) => setFiles(Array.from(event.target.files ?? []))} />
          </label>
          {files.map((file) => (
            <div key={`${file.name}-${file.size}`} className="flex items-center justify-between rounded-md border border-zinc-200 px-3 py-2">
              <span className="text-sm font-medium text-zinc-800">{file.name}</span>
              <Badge>{formatBytes(file.size)}</Badge>
            </div>
          ))}
          <Button disabled={!selectedKbId || !files.length || isBusy} onClick={uploadAndIndex}>
            <Play className="h-4 w-4" aria-hidden />
            Upload and index
          </Button>
        </div>
      ) : null}
      {sourceType === "web" ? (
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <Label>Source name</Label>
            <Input value={connectorName} onChange={(event) => setConnectorName(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Company profile name</Label>
            <Input value={companyName} onChange={(event) => setCompanyName(event.target.value)} />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>Seed URLs</Label>
            <Input value={seedUrls} onChange={(event) => setSeedUrls(event.target.value)} placeholder="https://example.com, https://example.com/docs" />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>Allowlist domains</Label>
            <Input value={allowlist} onChange={(event) => setAllowlist(event.target.value)} placeholder="example.com" />
          </div>
          <Button disabled={!seedUrls || !selectedKbId || isBusy} onClick={() => saveConnector(true)}>
            <Save className="h-4 w-4" aria-hidden />
            Save and sync
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
            <div className="space-y-2">
              <Label>Enabled tool names</Label>
              <Input value={enabledToolNames} onChange={(event) => setEnabledToolNames(event.target.value)} placeholder="search,lookup" />
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
}: {
  connectors: ConnectorConnection[];
  activeConnectionId: string;
  setActiveConnectionId: (id: string) => void;
  onTest: (connection: ConnectorConnection) => void;
  onSync: (connection: ConnectorConnection) => void;
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
  return (
    <Panel className="overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3">
        <h3 className="font-semibold text-zinc-950">Company data</h3>
        <Select className="max-w-64" value={selectedKbId} onChange={(event) => setSelectedKbId(event.target.value)}>
          <option value="">All knowledge bases</option>
          {kbs.map((kb) => (
            <option key={kb.id} value={kb.id}>
              {kb.name}
            </option>
          ))}
        </Select>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-zinc-200 text-sm">
          <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
            <tr>
              <th className="px-4 py-3">Document</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Security</th>
              <th className="px-4 py-3">Updated</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 bg-white">
            {docs.slice(0, 12).map((doc) => (
              <tr key={doc.id}>
                <td className="px-4 py-3">
                  <p className="font-medium text-zinc-950">{doc.name}</p>
                  <p className="text-xs text-zinc-500">{doc.source_url ?? doc.original_filename}</p>
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={doc.processing_status} />
                </td>
                <td className="px-4 py-3">{doc.confidentiality}</td>
                <td className="px-4 py-3 text-zinc-600">{shortDate(doc.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!docs.length ? <EmptyState icon={FileText} title="No documents yet" body="Add a source to create indexed company data." /> : null}
    </Panel>
  );
}

function ReviewPanel({
  documents,
  pipelines,
  selectedDocId,
  setSelectedDocId,
  qualityReport,
  onReview,
}: {
  documents: DocumentRecord[];
  pipelines: PipelineRun[];
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
        {pipelines.map((run) => (
          <Link key={run.id} href={`/pipeline/${run.id}`} className="block rounded-md border border-zinc-200 p-3 hover:bg-zinc-50">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium text-zinc-950">Pipeline {shortDate(run.created_at)}</span>
              <StatusBadge status={run.current_stage} />
            </div>
            <p className="mt-1 text-xs text-zinc-500">
              {run.processed_count}/{run.total_count} document(s), {run.errors.length} error(s), {run.warnings.length} warning(s)
            </p>
          </Link>
        ))}
        {!documents.length && !pipelines.length ? <p className="text-sm text-zinc-500">No review items right now.</p> : null}
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

function ProfileSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ id: string; name: string }>;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Default</option>
        {options.map((profile) => (
          <option key={profile.id} value={profile.id}>
            {profile.name}
          </option>
        ))}
      </Select>
    </div>
  );
}

function splitList(value: string) {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
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
