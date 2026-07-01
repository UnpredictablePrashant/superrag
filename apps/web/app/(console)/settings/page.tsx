"use client";

import { ErrorBox } from "@/components/error-box";
import { StatusBadge } from "@/components/status-badge";
import {
  api,
  createChatProfile,
  createEmbeddingProfile,
  getMe,
  getTelegramIntegration,
  listConnectors,
  listKnowledgeBases,
  listMembers,
  listProfiles,
  listProviderModels,
  listTelegramAllowedUsers,
  updateChatProfile,
  updateKnowledgeBase,
  ConnectorConnection,
  ConnectorRun,
  ModelOption,
  ProfilesResponse,
  ProviderConnection,
  TelegramAllowedUser,
} from "@/lib/api";
import { shortDate } from "@/lib/format";
import { Badge, Button, Input, Label, Panel, Select, Textarea } from "@rag-console/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Bot, Globe, History, KeyRound, Play, Plug, RotateCw, Save, Send, ShieldCheck, SlidersHorizontal, Trash2, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

const tabs = [
  "RAG Settings",
  "Organization",
  "AI Providers",
  "Model Profiles",
  "Connectors",
  "Telegram",
  "Notifications",
  "Security",
  "Audit Logs",
];

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

export default function SettingsPage() {
  const router = useRouter();
  const [tab, setTab] = React.useState("RAG Settings");
  const me = useQuery({ queryKey: ["me"], queryFn: getMe });
  const canManageSettings = me.data?.role === "Owner" || me.data?.role === "Admin";
  React.useEffect(() => {
    if (me.data && !canManageSettings) router.replace("/ask");
  }, [canManageSettings, me.data, router]);
  if (me.isLoading || !canManageSettings) {
    return <div className="text-sm text-zinc-500">Loading settings</div>;
  }
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-zinc-950">Admin Settings</h2>
        <p className="mt-1 text-sm text-zinc-500">Manage tenant configuration, AI providers, security, and audit history.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {tabs.map((item) => (
          <button
            key={item}
            className={`rounded-md px-3 py-2 text-sm font-medium ${
              tab === item ? "bg-emerald-600 text-white" : "bg-white text-zinc-700 hover:bg-zinc-100"
            }`}
            onClick={() => setTab(item)}
          >
            {item}
          </button>
        ))}
      </div>
      {tab === "RAG Settings" ? <RagSettings /> : null}
      {tab === "Organization" ? <OrganizationSettings /> : null}
      {tab === "AI Providers" ? <ProviderSettings /> : null}
      {tab === "Model Profiles" ? <ProfileSettings /> : null}
      {tab === "Connectors" ? <ConnectorSettings /> : null}
      {tab === "Telegram" ? <TelegramSettings /> : null}
      {tab === "Notifications" ? <Notifications /> : null}
      {tab === "Security" ? <SecuritySettings /> : null}
      {tab === "Audit Logs" ? <AuditLogs /> : null}
    </div>
  );
}

function RagSettings() {
  const queryClient = useQueryClient();
  const kbs = useQuery({ queryKey: ["knowledge-bases"], queryFn: listKnowledgeBases });
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: listProfiles });
  const [selectedKbId, setSelectedKbId] = React.useState("");
  const [cleanupProfileId, setCleanupProfileId] = React.useState("");
  const [chunkingProfileId, setChunkingProfileId] = React.useState("");
  const [embeddingProfileId, setEmbeddingProfileId] = React.useState("");
  const [retrievalAlgorithm, setRetrievalAlgorithm] = React.useState("hybrid_rrf");
  const [maxChunks, setMaxChunks] = React.useState("8");
  const [vectorCandidates, setVectorCandidates] = React.useState("40");
  const [keywordCandidates, setKeywordCandidates] = React.useState("40");
  const [rerankCandidates, setRerankCandidates] = React.useState("20");
  const [rrfConstant, setRrfConstant] = React.useState("60");
  const [similarityThreshold, setSimilarityThreshold] = React.useState("0.1");
  const [indexingStrategy, setIndexingStrategy] = React.useState("full_replace_chunks_and_vectors");
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");

  const selectedKb = (kbs.data ?? []).find((kb) => kb.id === selectedKbId);

  React.useEffect(() => {
    if (!selectedKbId && kbs.data?.[0]) setSelectedKbId(kbs.data[0].id);
  }, [kbs.data, selectedKbId]);

  React.useEffect(() => {
    if (!profiles.data) return;
    const recommended = recommendedRagDefaults(profiles.data);
    setCleanupProfileId(selectedKb?.default_cleanup_profile_id ?? recommended.cleanupProfileId);
    setChunkingProfileId(selectedKb?.default_chunking_profile_id ?? recommended.chunkingProfileId);
    setEmbeddingProfileId(selectedKb?.default_embedding_profile_id ?? recommended.embeddingProfileId);
    const config = selectedKb?.default_retrieval_config ?? {};
    setRetrievalAlgorithm(stringSetting(config.retrieval_algorithm, "hybrid_rrf"));
    setMaxChunks(stringSetting(config.max_chunks, "8"));
    setVectorCandidates(stringSetting(config.vector_candidate_count, "40"));
    setKeywordCandidates(stringSetting(config.keyword_candidate_count, "40"));
    setRerankCandidates(stringSetting(config.rerank_candidates, "20"));
    setRrfConstant(stringSetting(config.rrf_constant, "60"));
    setSimilarityThreshold(stringSetting(config.similarity_threshold, "0.1"));
    setIndexingStrategy(stringSetting(config.indexing_strategy, "full_replace_chunks_and_vectors"));
  }, [profiles.data, selectedKb]);

  function applyRecommended() {
    if (!profiles.data) return;
    const recommended = recommendedRagDefaults(profiles.data);
    setCleanupProfileId(recommended.cleanupProfileId);
    setChunkingProfileId(recommended.chunkingProfileId);
    setEmbeddingProfileId(recommended.embeddingProfileId);
    setRetrievalAlgorithm("hybrid_rrf");
    setMaxChunks("8");
    setVectorCandidates("40");
    setKeywordCandidates("40");
    setRerankCandidates("20");
    setRrfConstant("60");
    setSimilarityThreshold("0.1");
    setIndexingStrategy("full_replace_chunks_and_vectors");
  }

  async function saveDefaults() {
    if (!selectedKbId) {
      setError("Select a knowledge base first.");
      return;
    }
    setError("");
    setNotice("");
    try {
      await updateKnowledgeBase(selectedKbId, {
        default_cleanup_profile_id: cleanupProfileId || null,
        default_chunking_profile_id: chunkingProfileId || null,
        default_embedding_profile_id: embeddingProfileId || null,
        default_retrieval_config: {
          retrieval_algorithm: retrievalAlgorithm,
          max_chunks: numberOrDefault(maxChunks, 8),
          vector_candidate_count: numberOrDefault(vectorCandidates, 40),
          keyword_candidate_count: numberOrDefault(keywordCandidates, 40),
          rerank_candidates: numberOrDefault(rerankCandidates, 20),
          rrf_constant: numberOrDefault(rrfConstant, 60),
          similarity_threshold: decimalOrDefault(similarityThreshold, 0.1),
          indexing_strategy: indexingStrategy,
        },
      });
      setNotice("RAG defaults saved. Data Hub uploads and web syncs will use these settings.");
      queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
      queryClient.invalidateQueries({ queryKey: ["workspace-summary"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save RAG settings.");
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_0.8fr]">
      <Panel className="p-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <SlidersHorizontal className="h-5 w-5 text-emerald-700" aria-hidden />
              <h3 className="font-semibold text-zinc-950">RAG Settings</h3>
            </div>
            <p className="mt-1 text-sm text-zinc-500">Default processing pipeline used by Data Hub uploads, web syncs, reindexing, and Ask retrieval.</p>
          </div>
          <Button variant="secondary" onClick={applyRecommended}>
            Recommended defaults
          </Button>
        </div>
        <ErrorBox message={error} />
        {notice ? <div className="mt-3 rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</div> : null}
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <div className="space-y-2 md:col-span-2">
            <Label>Knowledge base</Label>
            <Select value={selectedKbId} onChange={(event) => setSelectedKbId(event.target.value)}>
              <option value="">Select knowledge base</option>
              {(kbs.data ?? []).map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name}
                </option>
              ))}
            </Select>
          </div>
          <ProfileSelect label="Cleaning" value={cleanupProfileId} onChange={setCleanupProfileId} options={profiles.data?.cleanup_profiles ?? []} />
          <ProfileSelect label="Chunking" value={chunkingProfileId} onChange={setChunkingProfileId} options={profiles.data?.chunking_profiles ?? []} />
          <ProfileSelect
            label="Embedding"
            value={embeddingProfileId}
            onChange={setEmbeddingProfileId}
            options={(profiles.data?.embedding_profiles ?? []).map((profile) => ({
              id: profile.id,
              name: `${profile.name} / ${profile.model_name}`,
            }))}
          />
          <div className="space-y-2">
            <Label>Retrieval</Label>
            <Select value={retrievalAlgorithm} onChange={(event) => setRetrievalAlgorithm(event.target.value)}>
              <option value="hybrid_rrf">Hybrid RRF</option>
              <option value="vector">Vector only</option>
              <option value="keyword">Keyword only</option>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Indexing</Label>
            <Select value={indexingStrategy} onChange={(event) => setIndexingStrategy(event.target.value)}>
              <option value="full_replace_chunks_and_vectors">Full reindex</option>
              <option value="incremental_new_documents">Incremental new documents</option>
              <option value="embedding_backfill">Embedding backfill</option>
            </Select>
          </div>
          <NumberField label="Answer chunks" value={maxChunks} onChange={setMaxChunks} min={1} max={30} />
          <NumberField label="Vector candidates" value={vectorCandidates} onChange={setVectorCandidates} min={1} max={200} />
          <NumberField label="Keyword candidates" value={keywordCandidates} onChange={setKeywordCandidates} min={1} max={200} />
          <NumberField label="Rerank candidates" value={rerankCandidates} onChange={setRerankCandidates} min={1} max={100} />
          <NumberField label="RRF constant" value={rrfConstant} onChange={setRrfConstant} min={1} max={200} />
          <NumberField label="Similarity threshold" value={similarityThreshold} onChange={setSimilarityThreshold} min={0} max={1} step="0.01" />
        </div>
        <Button className="mt-5" disabled={!selectedKbId} onClick={saveDefaults}>
          <Save className="h-4 w-4" aria-hidden />
          Save RAG defaults
        </Button>
      </Panel>

      <Panel className="p-5">
        <h3 className="font-semibold text-zinc-950">Current default flow</h3>
        <div className="mt-4 space-y-3 text-sm">
          <RagFlowStep label="1. Clean" value={profileName(profiles.data?.cleanup_profiles, cleanupProfileId)} />
          <RagFlowStep label="2. Chunk" value={profileName(profiles.data?.chunking_profiles, chunkingProfileId)} />
          <RagFlowStep label="3. Embed" value={profileName(profiles.data?.embedding_profiles, embeddingProfileId)} />
          <RagFlowStep label="4. Index" value={indexingStrategyLabel(indexingStrategy)} />
          <RagFlowStep label="5. Retrieve" value={`${retrievalAlgorithmLabel(retrievalAlgorithm)} / ${maxChunks} chunks`} />
        </div>
      </Panel>
    </div>
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
        <option value="">Recommended default</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </Select>
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  min: number;
  max: number;
  step?: number | string;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Input type="number" value={value} onChange={(event) => onChange(event.target.value)} min={min} max={max} step={step} />
    </div>
  );
}

function RagFlowStep({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-zinc-200 p-3">
      <p className="text-xs font-medium uppercase text-zinc-500">{label}</p>
      <p className="mt-1 font-medium text-zinc-950">{value || "Recommended default"}</p>
    </div>
  );
}

function recommendedRagDefaults(profiles: ProfilesResponse) {
  const cleanup =
    profiles.cleanup_profiles.find((profile) => profile.name === "Standard Enterprise Cleanup") ??
    profiles.cleanup_profiles[1] ??
    profiles.cleanup_profiles[0];
  const chunking =
    profiles.chunking_profiles.find((profile) => profile.name === "Document-Aware Chunking") ??
    profiles.chunking_profiles.find((profile) => profile.name === "Recursive Token Chunking") ??
    profiles.chunking_profiles[0];
  const embedding = profiles.embedding_profiles.find((profile) => profile.is_active) ?? profiles.embedding_profiles[0];
  return {
    cleanupProfileId: cleanup?.id ?? "",
    chunkingProfileId: chunking?.id ?? "",
    embeddingProfileId: embedding?.id ?? "",
  };
}

function profileName(profiles: Array<{ id: string; name: string }> | undefined, id: string) {
  return profiles?.find((profile) => profile.id === id)?.name ?? "Recommended default";
}

function stringSetting(value: unknown, fallback: string) {
  if (typeof value === "string" && value) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return fallback;
}

function numberOrDefault(value: string, fallback: number) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function decimalOrDefault(value: string, fallback: number) {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function indexingStrategyLabel(value: string) {
  if (value === "incremental_new_documents") return "Incremental new documents";
  if (value === "embedding_backfill") return "Embedding backfill";
  return "Full reindex";
}

function retrievalAlgorithmLabel(value: string) {
  if (value === "vector") return "Vector only";
  if (value === "keyword") return "Keyword only";
  return "Hybrid RRF";
}

function OrganizationSettings() {
  const queryClient = useQueryClient();
  const org = useQuery({ queryKey: ["organization"], queryFn: () => api<{ id: string; name: string; settings: Record<string, unknown> }>("/organizations/current") });
  const [name, setName] = React.useState("");
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    if (org.data?.name) setName(org.data.name);
  }, [org.data?.name]);
  async function save() {
    try {
      await api("/organizations/current", { method: "PATCH", body: JSON.stringify({ name }) });
      queryClient.invalidateQueries({ queryKey: ["organization"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save organization.");
    }
  }
  return (
    <Panel className="p-5">
      <ErrorBox message={error} />
      <div className="mt-4 max-w-lg space-y-2">
        <Label htmlFor="org-name">Organization name</Label>
        <Input id="org-name" value={name} onChange={(event) => setName(event.target.value)} />
      </div>
      <Button className="mt-4" onClick={save}>
        <Save className="h-4 w-4" aria-hidden />
        Save
      </Button>
    </Panel>
  );
}

function ProviderSettings() {
  const queryClient = useQueryClient();
  const [provider, setProvider] = React.useState("OpenAI");
  const [name, setName] = React.useState("");
  const [apiKey, setApiKey] = React.useState("");
  const [baseUrl, setBaseUrl] = React.useState("");
  const [error, setError] = React.useState("");
  const connections = useQuery({
    queryKey: ["provider-connections"],
    queryFn: () => api<ProviderConnection[]>("/provider-connections"),
  });
  const modelOptions = useQuery({
    queryKey: ["provider-models"],
    queryFn: () => listProviderModels(),
  });
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: listProfiles });
  const create = useMutation({
    mutationFn: () =>
      api("/provider-connections", {
        method: "POST",
        body: JSON.stringify({
          provider,
          name: name || `${provider} connection`,
          api_key: apiKey,
          base_url: baseUrl || undefined,
        }),
      }),
    onSuccess: () => {
      setName("");
      setApiKey("");
      setBaseUrl("");
      queryClient.invalidateQueries({ queryKey: ["provider-connections"] });
      queryClient.invalidateQueries({ queryKey: ["provider-models"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not save provider."),
  });
  const createEmbedding = useMutation({
    mutationFn: (option: ModelOption) =>
      createEmbeddingProfile({
        provider_connection_id: option.provider_connection_id ?? null,
        name:
          option.provider === "Local"
            ? "Local deterministic embedding"
            : `${option.connection_name} ${option.model}`,
        model_name: option.model,
        embedding_dimension: option.embedding_dimension ?? (option.provider === "Local" ? 384 : 1536),
        batch_size: 64,
        normalization: "l2",
        is_active: true,
        config: {
          provider: option.provider,
          connection_name: option.connection_name,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profiles"] });
      setError("");
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not create embedding profile."),
  });
  const createChat = useMutation({
    mutationFn: (option: ModelOption) =>
      createChatProfile({
        provider_connection_id: option.provider_connection_id ?? null,
        name: `${option.connection_name} ${option.model}`,
        model_name: option.model,
        supports_streaming: option.supports_streaming,
        supports_structured_output: option.supports_structured_output,
        context_window: option.maximum_context_window ?? null,
        max_output_tokens: option.maximum_output_tokens ?? null,
        is_default: !(profiles.data?.chat_profiles ?? []).some((profile) => profile.is_default),
        config: {
          provider: option.provider,
          connection_name: option.connection_name,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profiles"] });
      setError("");
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not create LLM profile."),
  });

  const chatOptions = (modelOptions.data ?? []).filter((option) => option.supports_chat && option.provider_connection_id);
  const embeddingOptions = (modelOptions.data ?? []).filter(
    (option) => option.supports_embeddings && ["Local", "OpenAI"].includes(option.provider),
  );
  const existingChatProfiles = profiles.data?.chat_profiles ?? [];
  const existingEmbeddingProfiles = profiles.data?.embedding_profiles ?? [];

  async function test(id: string) {
    setError("");
    try {
      await api(`/provider-connections/${id}/test`, { method: "POST" });
      queryClient.invalidateQueries({ queryKey: ["provider-connections"] });
      queryClient.invalidateQueries({ queryKey: ["provider-models"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Provider test failed.");
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
      <Panel className="p-5">
        <div className="flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-emerald-700" aria-hidden />
          <h3 className="font-semibold text-zinc-950">Provider credentials</h3>
        </div>
        <ErrorBox message={error} />
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <div className="space-y-2">
            <Label>Provider</Label>
            <Select value={provider} onChange={(event) => setProvider(event.target.value)}>
              {["OpenAI", "Anthropic", "Google Gemini", "xAI Grok", "Local"].map((item) => (
                <option key={item}>{item}</option>
              ))}
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Name</Label>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>API key</Label>
            <Input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Base URL</Label>
            <Input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
          </div>
        </div>
        <Button className="mt-4" onClick={() => create.mutate()}>
          <Save className="h-4 w-4" aria-hidden />
          Save connection
        </Button>
        <div className="mt-5 divide-y divide-zinc-100">
          {(connections.data ?? []).map((connection) => (
            <div key={connection.id} className="flex items-center justify-between gap-3 py-3">
              <div>
                <p className="font-medium text-zinc-950">{connection.name}</p>
                <p className="text-sm text-zinc-500">
                  {connection.provider} {connection.masked_api_key ? `- ${connection.masked_api_key}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={connection.status} />
                <Button variant="secondary" onClick={() => test(connection.id)}>
                  <RotateCw className="h-4 w-4" aria-hidden />
                  Test
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Panel>
      <Panel className="p-5">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-5 w-5 text-sky-700" aria-hidden />
          <h3 className="font-semibold text-zinc-950">Configured model options</h3>
        </div>
        <div className="mt-4 rounded-md border border-zinc-200 p-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h4 className="font-medium text-zinc-950">LLM answer models</h4>
              <p className="mt-1 text-sm text-zinc-500">Create a chat model profile for synthesized answers.</p>
            </div>
            {createChat.isPending ? <Badge tone="amber">Saving</Badge> : null}
          </div>
          <div className="mt-3 space-y-2">
            {chatOptions.map((option, index) => {
              const existing = existingChatProfiles.find(
                (profile) =>
                  profile.provider === option.provider &&
                  profile.model_name === option.model &&
                  (profile.provider_connection_id ?? null) === (option.provider_connection_id ?? null),
              );
              return (
                <div key={`${option.provider}-${option.model}-${index}`} className="flex flex-col gap-2 rounded-md bg-zinc-50 p-3 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="text-sm font-medium text-zinc-950">
                      {option.provider} / {option.model}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {option.connection_name} / {option.maximum_context_window ? `${option.maximum_context_window.toLocaleString()} tokens` : "context unknown"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {existing?.is_default ? <Badge tone="green">Default</Badge> : existing ? <Badge tone="blue">Profile exists</Badge> : null}
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={createChat.isPending || existing?.is_default}
                      onClick={() => createChat.mutate(option)}
                    >
                      <Save className="h-4 w-4" aria-hidden />
                      {existing ? "Create default copy" : "Enable"}
                    </Button>
                  </div>
                </div>
              );
            })}
            {!chatOptions.length ? (
              <p className="text-sm text-zinc-500">Add and test an OpenAI, Anthropic, Gemini, or xAI provider connection to enable LLM answers.</p>
            ) : null}
          </div>
        </div>
        <div className="mt-4 rounded-md border border-zinc-200 p-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h4 className="font-medium text-zinc-950">Embedding options</h4>
              <p className="mt-1 text-sm text-zinc-500">Create an active Local or OpenAI embedding profile.</p>
            </div>
            {createEmbedding.isPending ? <Badge tone="amber">Saving</Badge> : null}
          </div>
          <div className="mt-3 space-y-2">
            {embeddingOptions.map((option, index) => {
              const existing = existingEmbeddingProfiles.find(
                (profile) =>
                  profile.provider === option.provider &&
                  profile.model_name === option.model &&
                  (profile.provider_connection_id ?? null) === (option.provider_connection_id ?? null),
              );
              return (
                <div key={`${option.provider}-${option.model}-${index}`} className="flex flex-col gap-2 rounded-md bg-zinc-50 p-3 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="text-sm font-medium text-zinc-950">
                      {option.provider} / {option.model}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {option.connection_name} / {option.embedding_dimension ?? "default"} dimensions
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {existing?.is_active ? <Badge tone="green">Active</Badge> : existing ? <Badge tone="blue">Profile exists</Badge> : null}
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={createEmbedding.isPending || existing?.is_active}
                      onClick={() => createEmbedding.mutate(option)}
                    >
                      <Save className="h-4 w-4" aria-hidden />
                      {existing ? "Make active copy" : "Enable"}
                    </Button>
                  </div>
                </div>
              );
            })}
            {!embeddingOptions.length ? (
              <p className="text-sm text-zinc-500">Local embeddings are available by default. Add an OpenAI connection to enable OpenAI embedding models.</p>
            ) : null}
          </div>
        </div>
        <div className="mt-4 max-h-[540px] space-y-2 overflow-auto">
          {(modelOptions.data ?? []).map((capability, index) => (
            <div key={`${capability.provider}-${capability.model}-${index}`} className="rounded-md bg-zinc-50 p-3 text-sm">
              <p className="font-medium text-zinc-950">
                {capability.provider} / {capability.model}
              </p>
              <p className="mt-1 text-zinc-500">
                {capability.connection_name} | chat {String(capability.supports_chat)} | embeddings{" "}
                {String(capability.supports_embeddings)}
              </p>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function ConnectorSettings() {
  const queryClient = useQueryClient();
  const connectors = useQuery({ queryKey: ["connectors"], queryFn: listConnectors });
  const kbs = useQuery({ queryKey: ["knowledge-bases"], queryFn: listKnowledgeBases });
  const [kind, setKind] = React.useState<"web" | "mcp">("web");
  const [scope, setScope] = React.useState<"user" | "organization">("user");
  const [name, setName] = React.useState("");
  const [baseUrl, setBaseUrl] = React.useState("");
  const [secret, setSecret] = React.useState("");
  const [seedUrls, setSeedUrls] = React.useState("");
  const [allowlist, setAllowlist] = React.useState("");
  const [companyName, setCompanyName] = React.useState("");
  const [mcpConfig, setMcpConfig] = React.useState(DEFAULT_MCP_CONFIG);
  const [syncKbId, setSyncKbId] = React.useState("");
  const [activeConnectionId, setActiveConnectionId] = React.useState("");
  const [enabled, setEnabled] = React.useState(true);
  const [discoveredTools, setDiscoveredTools] = React.useState<Record<string, McpToolSummary[]>>({});
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const runs = useQuery({
    queryKey: ["connector-runs", activeConnectionId],
    enabled: Boolean(activeConnectionId),
    queryFn: () => api<ConnectorRun[]>(`/connectors/${activeConnectionId}/runs`),
  });

  React.useEffect(() => {
    if (!syncKbId && kbs.data?.[0]) setSyncKbId(kbs.data[0].id);
  }, [kbs.data, syncKbId]);

  const create = useMutation({
    mutationFn: () => {
      const parsedMcpConfig = kind === "mcp" ? parseMcpConfig(mcpConfig) : {};
      const inferredTransport = kind === "mcp" ? inferMcpTransport(parsedMcpConfig, "stdio") : "streamable_http";
      const config =
        kind === "web"
          ? {
              seed_urls: splitList(seedUrls),
              allowlist_domains: splitList(allowlist),
              company_name: companyName || undefined,
              max_depth: 0,
            }
          : {
              ...parsedMcpConfig,
              transport: inferredTransport,
              disabled_tool_names: [],
            };
      return api("/connectors", {
        method: "POST",
        body: JSON.stringify({
          kind,
          scope,
          name: name || (kind === "web" ? "Web sync" : mcpServerName(config) ?? "MCP tools"),
          secret: secret || undefined,
          base_url: kind === "mcp" ? mcpBaseUrl(config) || baseUrl || undefined : baseUrl || undefined,
          is_enabled: enabled,
          config,
        }),
      });
    },
    onSuccess: () => {
      setName("");
      setBaseUrl("");
      setSecret("");
      setNotice("Connector saved.");
      queryClient.invalidateQueries({ queryKey: ["connectors"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not save connector."),
  });

  async function test(connection: ConnectorConnection) {
    setError("");
    setNotice("");
    const result = await api<{ status: string; message?: string; tools?: McpToolSummary[] }>(`/connectors/${connection.id}/test`, { method: "POST" });
    if (result.tools) {
      setDiscoveredTools((current) => ({ ...current, [connection.id]: result.tools ?? [] }));
    }
    setNotice(result.status === "ok" ? `Connector test passed. Detected ${result.tools?.length ?? 0} tool(s).` : result.message ?? "Connector test failed.");
    queryClient.invalidateQueries({ queryKey: ["connectors"] });
  }

  async function toggleConnector(connection: ConnectorConnection) {
    await api(`/connectors/${connection.id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_enabled: !connection.is_enabled }),
    });
    queryClient.invalidateQueries({ queryKey: ["connectors"] });
  }

  async function toggleTool(connection: ConnectorConnection, toolName: string) {
    const disabled = stringList(connection.config.disabled_tool_names);
    const nextDisabled = disabled.includes(toolName)
      ? disabled.filter((name) => name !== toolName)
      : [...disabled, toolName];
    await api(`/connectors/${connection.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        config: { ...connection.config, disabled_tool_names: nextDisabled },
      }),
    });
    queryClient.invalidateQueries({ queryKey: ["connectors"] });
  }

  async function sync(connection: ConnectorConnection) {
    setError("");
    setNotice("");
    if (!syncKbId) {
      setError("Choose a knowledge base before syncing.");
      return;
    }
    await api(`/connectors/${connection.id}/sync`, {
      method: "POST",
      body: JSON.stringify({
        knowledge_base_id: syncKbId,
        share_with_organization: connection.scope === "organization",
        options: { company_name: companyName || connection.config.company_name },
      }),
    });
    setActiveConnectionId(connection.id);
    setNotice("Connector sync queued.");
    queryClient.invalidateQueries({ queryKey: ["connector-runs", connection.id] });
  }

  async function remove(connection: ConnectorConnection) {
    await api(`/connectors/${connection.id}`, { method: "DELETE" });
    queryClient.invalidateQueries({ queryKey: ["connectors"] });
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
      <Panel className="p-5">
        <div className="flex items-center gap-2">
          <Plug className="h-5 w-5 text-emerald-700" aria-hidden />
          <h3 className="font-semibold text-zinc-950">Connector setup</h3>
        </div>
        <ErrorBox message={error} />
        {notice ? <div className="mt-3 rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</div> : null}
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <Label>Kind</Label>
            <Select value={kind} onChange={(event) => setKind(event.target.value as "web" | "mcp")}>
              <option value="web">Web crawl</option>
              <option value="mcp">MCP server</option>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Scope</Label>
            <Select value={scope} onChange={(event) => setScope(event.target.value as "user" | "organization")}>
              <option value="user">My connector</option>
              <option value="organization">Organization connector</option>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Name</Label>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          {kind === "web" ? (
            <div className="space-y-2">
              <Label>Base URL</Label>
              <Input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
            </div>
          ) : null}
          <div className="space-y-2">
            <Label>Secret</Label>
            <Input type="password" value={secret} onChange={(event) => setSecret(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Default knowledge base</Label>
            <Select value={syncKbId} onChange={(event) => setSyncKbId(event.target.value)}>
              <option value="">Select knowledge base</option>
              {(kbs.data ?? []).map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name}
                </option>
              ))}
            </Select>
          </div>
          {kind === "web" ? (
            <>
              <div className="space-y-2 md:col-span-2">
                <Label>Seed URLs</Label>
                <Input value={seedUrls} onChange={(event) => setSeedUrls(event.target.value)} placeholder="https://example.com, https://example.com/about" />
              </div>
              <div className="space-y-2">
                <Label>Allowlist domains</Label>
                <Input value={allowlist} onChange={(event) => setAllowlist(event.target.value)} placeholder="example.com" />
              </div>
              <div className="space-y-2">
                <Label>Company profile name</Label>
                <Input value={companyName} onChange={(event) => setCompanyName(event.target.value)} />
              </div>
            </>
          ) : (
            <>
              <div className="space-y-2 md:col-span-2">
                <Label>MCP JSON</Label>
                <Textarea
                  className="min-h-64 font-mono text-xs"
                  value={mcpConfig}
                  onChange={(event) => setMcpConfig(event.target.value)}
                  spellCheck={false}
                />
              </div>
            </>
          )}
          <label className="flex items-center gap-2 text-sm text-zinc-700">
            <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
            Enabled
          </label>
        </div>
        <Button className="mt-4" onClick={() => create.mutate()}>
          <Save className="h-4 w-4" aria-hidden />
          Save connector
        </Button>
      </Panel>

      <Panel className="p-5">
        <div className="flex items-center gap-2">
          <Globe className="h-5 w-5 text-sky-700" aria-hidden />
          <h3 className="font-semibold text-zinc-950">Available connectors</h3>
        </div>
        <div className="mt-4 divide-y divide-zinc-100">
          {(connectors.data ?? []).map((connection) => (
            <div key={connection.id} className="py-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium text-zinc-950">{connection.name}</p>
                  <p className="text-sm text-zinc-500">
                    {connection.kind} / {connection.scope} {connection.masked_secret ? `- ${connection.masked_secret}` : ""}
                  </p>
                  <div className="mt-2 flex gap-2">
                    <StatusBadge status={connection.status} />
                    {connection.is_enabled ? <Badge tone="green">Enabled</Badge> : <Badge>Paused</Badge>}
                  </div>
                  {connection.kind === "mcp" ? (
                    <ToolToggleList connection={connection} tools={toolsForConnection(connection, discoveredTools[connection.id])} onToggle={toggleTool} />
                  ) : null}
                </div>
                <div className="flex gap-2">
                  <Button variant="ghost" size="icon" onClick={() => setActiveConnectionId(connection.id)}>
                    <History className="h-4 w-4" aria-hidden />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => remove(connection)}>
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </Button>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="secondary" onClick={() => test(connection)}>
                  <RotateCw className="h-4 w-4" aria-hidden />
                  Test
                </Button>
                <Button variant="secondary" onClick={() => toggleConnector(connection)}>
                  {connection.is_enabled ? "Pause" : "Enable"}
                </Button>
                <Button variant="secondary" onClick={() => sync(connection)}>
                  <Play className="h-4 w-4" aria-hidden />
                  Sync
                </Button>
              </div>
            </div>
          ))}
        </div>
        {activeConnectionId ? (
          <div className="mt-5 rounded-md bg-zinc-50 p-3">
            <p className="font-medium text-zinc-950">Sync history</p>
            <div className="mt-2 space-y-2">
              {(runs.data ?? []).map((run) => (
                <div key={run.id} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-zinc-600">{shortDate(run.created_at)}</span>
                  <StatusBadge status={run.status} />
                  <span className="text-zinc-500">
                    {run.processed_items}/{run.total_items}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </Panel>
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

interface McpToolSummary {
  name: string;
  description?: string;
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

function stringList(value: unknown) {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function toolsForConnection(connection: ConnectorConnection, freshTools?: McpToolSummary[]) {
  if (freshTools?.length) return freshTools;
  const cached = connection.config.discovered_tools;
  if (!Array.isArray(cached)) return [];
  return cached
    .filter((tool): tool is Record<string, unknown> => Boolean(tool) && typeof tool === "object" && !Array.isArray(tool))
    .map((tool) => ({ name: String(tool.name ?? ""), description: String(tool.description ?? "") }))
    .filter((tool) => tool.name);
}

function ToolToggleList({
  connection,
  tools,
  onToggle,
}: {
  connection: ConnectorConnection;
  tools: McpToolSummary[];
  onToggle: (connection: ConnectorConnection, toolName: string) => void;
}) {
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
            <input type="checkbox" checked={active} onChange={() => onToggle(connection, tool.name)} />
          </label>
        );
      })}
    </div>
  );
}

function ProfileSettings() {
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: listProfiles });
  return <ModelProfileSettings profiles={profiles.data} />;
}

function ModelProfileSettings({ profiles }: { profiles?: ProfilesResponse }) {
  const queryClient = useQueryClient();
  const models = useQuery({ queryKey: ["provider-models"], queryFn: () => listProviderModels() });
  const chatOptions = (models.data ?? []).filter((option) => option.supports_chat);
  const [selectedKey, setSelectedKey] = React.useState("");
  const [name, setName] = React.useState("");
  const [error, setError] = React.useState("");
  const selected = chatOptions.find((option) => optionKey(option) === selectedKey) ?? chatOptions[0];
  React.useEffect(() => {
    if (!selectedKey && chatOptions[0]) setSelectedKey(optionKey(chatOptions[0]));
  }, [chatOptions, selectedKey]);
  const create = useMutation({
    mutationFn: () =>
      createChatProfile({
        provider_connection_id: selected?.provider_connection_id || undefined,
        name: name || `${selected?.provider ?? "Local"} ${selected?.model ?? "model"}`,
        model_name: selected?.model ?? "",
        supports_streaming: selected?.supports_streaming ?? false,
        supports_structured_output: selected?.supports_structured_output ?? false,
        context_window: selected?.maximum_context_window || undefined,
        max_output_tokens: selected?.maximum_output_tokens || undefined,
        is_default: !(profiles?.chat_profiles ?? []).some((profile) => profile.is_default),
        config: { provider: selected?.provider },
      }),
    onSuccess: () => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["profiles"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not create model profile."),
  });
  async function updateProfile(id: string, patch: { is_enabled?: boolean; is_default?: boolean }) {
    setError("");
    try {
      await updateChatProfile(id, patch);
      queryClient.invalidateQueries({ queryKey: ["profiles"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update model profile.");
    }
  }
  return (
    <Panel className="p-5">
      <h3 className="font-semibold text-zinc-950">Model Profiles</h3>
      <ErrorBox message={error} />
      <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_1fr_auto]">
        <div className="space-y-2">
          <Label>Chat model</Label>
          <Select value={selectedKey} onChange={(event) => setSelectedKey(event.target.value)}>
            {chatOptions.map((option) => (
              <option key={optionKey(option)} value={optionKey(option)}>
                {option.provider} / {option.model} ({option.connection_name})
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Profile name</Label>
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </div>
        <div className="flex items-end">
          <Button disabled={!selected || create.isPending} onClick={() => create.mutate()}>
            <Save className="h-4 w-4" aria-hidden />
            Create
          </Button>
        </div>
      </div>
      <ProfileCards profiles={profiles?.chat_profiles ?? []} onUpdate={updateProfile} />
    </Panel>
  );
}

function ProfileCards({
  profiles,
  onUpdate,
}: {
  profiles: Array<{
    id: string;
    name: string;
    provider?: unknown;
    model_name?: unknown;
    strategy?: unknown;
    is_active?: unknown;
    is_default?: unknown;
    is_enabled?: unknown;
  }>;
  onUpdate?: (id: string, patch: { is_enabled?: boolean; is_default?: boolean }) => void;
}) {
  return (
    <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {profiles.map((profile) => (
        <div key={String(profile.id)} className="rounded-md border border-zinc-200 p-4">
          <p className="font-medium text-zinc-950">{String(profile.name)}</p>
          <p className="mt-1 text-sm text-zinc-500">
            {String(profile.provider ?? "Local")} / {String(profile.model_name ?? profile.strategy ?? "")}
          </p>
          {"is_active" in profile && profile.is_active ? <Badge tone="green">Active</Badge> : null}
          {"is_default" in profile && profile.is_default ? <Badge tone="blue">Default</Badge> : null}
          {"is_enabled" in profile ? (
            <div className="mt-3 flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => onUpdate?.(String(profile.id), { is_enabled: !profile.is_enabled })}>
                {profile.is_enabled ? "Disable" : "Enable"}
              </Button>
              <Button variant="ghost" disabled={Boolean(profile.is_default)} onClick={() => onUpdate?.(String(profile.id), { is_default: true })}>
                Set default
              </Button>
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function optionKey(option: ModelOption) {
  return `${option.provider_connection_id ?? "local"}::${option.model}`;
}

function TelegramSettings() {
  const queryClient = useQueryClient();
  const integration = useQuery({ queryKey: ["telegram-integration"], queryFn: getTelegramIntegration });
  const allowedUsers = useQuery({ queryKey: ["telegram-allowed-users"], queryFn: listTelegramAllowedUsers });
  const members = useQuery({ queryKey: ["members"], queryFn: listMembers });
  const kbs = useQuery({ queryKey: ["knowledge-bases"], queryFn: listKnowledgeBases });
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: listProfiles });
  const [botToken, setBotToken] = React.useState("");
  const [botUsername, setBotUsername] = React.useState("");
  const [defaultKbId, setDefaultKbId] = React.useState("");
  const [chatProfileId, setChatProfileId] = React.useState("");
  const [autoText, setAutoText] = React.useState(true);
  const [autoDocs, setAutoDocs] = React.useState(true);
  const [autoVoice, setAutoVoice] = React.useState(true);
  const [enabled, setEnabled] = React.useState(false);
  const [userDraft, setUserDraft] = React.useState({
    username: "",
    phone_number: "",
    display_name: "",
    user_id: "",
    can_ingest: true,
    can_query: true,
  });
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");

  React.useEffect(() => {
    const data = integration.data;
    if (!data) return;
    setBotUsername(data.bot_username ?? "");
    setDefaultKbId(data.default_knowledge_base_id ?? "");
    setChatProfileId(data.default_chat_model_profile_id ?? "");
    setAutoText(data.auto_ingest_text);
    setAutoDocs(data.auto_ingest_documents);
    setAutoVoice(data.auto_ingest_voice);
    setEnabled(data.is_enabled);
  }, [integration.data]);

  async function saveIntegration() {
    setError("");
    setNotice("");
    try {
      await api("/integrations/telegram", {
        method: "PATCH",
        body: JSON.stringify({
          bot_token: botToken || undefined,
          bot_username: botUsername || undefined,
          default_knowledge_base_id: defaultKbId || undefined,
          default_chat_model_profile_id: chatProfileId || undefined,
          auto_ingest_text: autoText,
          auto_ingest_documents: autoDocs,
          auto_ingest_voice: autoVoice,
          is_enabled: enabled,
        }),
      });
      setBotToken("");
      setNotice("Telegram settings saved.");
      queryClient.invalidateQueries({ queryKey: ["telegram-integration"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save Telegram settings.");
    }
  }

  async function testBot() {
    setError("");
    setNotice("");
    try {
      const result = await api<{ bot: { username?: string } }>("/integrations/telegram/test", { method: "POST" });
      setNotice(`Connected to @${result.bot.username ?? "telegram bot"}.`);
      queryClient.invalidateQueries({ queryKey: ["telegram-integration"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Telegram bot test failed.");
    }
  }

  async function registerWebhook() {
    setError("");
    setNotice("");
    try {
      await api("/integrations/telegram/register-webhook", { method: "POST" });
      setNotice("Telegram webhook registered.");
      queryClient.invalidateQueries({ queryKey: ["telegram-integration"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not register webhook.");
    }
  }

  async function addAllowedUser() {
    setError("");
    setNotice("");
    try {
      await api("/integrations/telegram/allowed-users", {
        method: "POST",
        body: JSON.stringify({
          username: userDraft.username || undefined,
          phone_number: userDraft.phone_number || undefined,
          display_name: userDraft.display_name || undefined,
          user_id: userDraft.user_id || undefined,
          can_ingest: userDraft.can_ingest,
          can_query: userDraft.can_query,
        }),
      });
      setUserDraft({
        username: "",
        phone_number: "",
        display_name: "",
        user_id: "",
        can_ingest: true,
        can_query: true,
      });
      queryClient.invalidateQueries({ queryKey: ["telegram-allowed-users"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add Telegram user.");
    }
  }

  async function removeAllowedUser(user: TelegramAllowedUser) {
    await api(`/integrations/telegram/allowed-users/${user.id}`, { method: "DELETE" });
    queryClient.invalidateQueries({ queryKey: ["telegram-allowed-users"] });
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
      <Panel className="p-5">
        <div className="flex items-center gap-2">
          <Bot className="h-5 w-5 text-sky-700" aria-hidden />
          <h3 className="font-semibold text-zinc-950">Telegram bot</h3>
        </div>
        <ErrorBox message={error} />
        {notice ? <div className="mt-3 rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</div> : null}
        <div className="mt-4 grid gap-3 md:grid-cols-2">
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
            <Select value={defaultKbId} onChange={(event) => setDefaultKbId(event.target.value)}>
              <option value="">Select knowledge base</option>
              {(kbs.data ?? []).map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Answer/refine model</Label>
            <Select value={chatProfileId} onChange={(event) => setChatProfileId(event.target.value)}>
              <option value="">Default chat model</option>
              {(profiles.data?.chat_profiles ?? []).map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.provider} / {profile.model_name}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-3 rounded-md bg-zinc-50 p-3">
            <label className="flex items-center gap-2 text-sm text-zinc-700">
              <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
              Enabled
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700">
              <input type="checkbox" checked={autoText} onChange={(event) => setAutoText(event.target.checked)} />
              Ingest text
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700">
              <input type="checkbox" checked={autoDocs} onChange={(event) => setAutoDocs(event.target.checked)} />
              Ingest documents
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700">
              <input type="checkbox" checked={autoVoice} onChange={(event) => setAutoVoice(event.target.checked)} />
              Ingest voice
            </label>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button onClick={saveIntegration}>
            <Save className="h-4 w-4" aria-hidden />
            Save
          </Button>
          <Button variant="secondary" onClick={testBot}>
            <Send className="h-4 w-4" aria-hidden />
            Test
          </Button>
          <Button variant="secondary" onClick={registerWebhook}>
            <RotateCw className="h-4 w-4" aria-hidden />
            Register webhook
          </Button>
        </div>
        {integration.data ? (
          <div className="mt-5 space-y-2 rounded-md bg-zinc-50 p-3 text-sm text-zinc-600">
            <p className="font-medium text-zinc-950">Webhook</p>
            <p className="break-all">{integration.data.webhook_url}</p>
            <p className="break-all">Secret: {integration.data.webhook_secret_token}</p>
          </div>
        ) : null}
      </Panel>

      <Panel className="p-5">
        <div className="flex items-center gap-2">
          <UserPlus className="h-5 w-5 text-emerald-700" aria-hidden />
          <h3 className="font-semibold text-zinc-950">Allowed Telegram users</h3>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <Label>Username</Label>
            <Input value={userDraft.username} onChange={(event) => setUserDraft({ ...userDraft, username: event.target.value })} />
          </div>
          <div className="space-y-2">
            <Label>Phone</Label>
            <Input value={userDraft.phone_number} onChange={(event) => setUserDraft({ ...userDraft, phone_number: event.target.value })} />
          </div>
          <div className="space-y-2">
            <Label>RAG account</Label>
            <Select value={userDraft.user_id} onChange={(event) => setUserDraft({ ...userDraft, user_id: event.target.value })}>
              <option value="">Not linked</option>
              {(members.data ?? []).map((member) => (
                <option key={member.id} value={member.user_id}>
                  {member.email}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>Display name</Label>
            <Input value={userDraft.display_name} onChange={(event) => setUserDraft({ ...userDraft, display_name: event.target.value })} />
          </div>
          <label className="flex items-center gap-2 text-sm text-zinc-700">
            <input type="checkbox" checked={userDraft.can_ingest} onChange={(event) => setUserDraft({ ...userDraft, can_ingest: event.target.checked })} />
            Can ingest
          </label>
          <label className="flex items-center gap-2 text-sm text-zinc-700">
            <input type="checkbox" checked={userDraft.can_query} onChange={(event) => setUserDraft({ ...userDraft, can_query: event.target.checked })} />
            Can ask
          </label>
        </div>
        <Button className="mt-4" disabled={!userDraft.username && !userDraft.phone_number} onClick={addAllowedUser}>
          <UserPlus className="h-4 w-4" aria-hidden />
          Add user
        </Button>
        <div className="mt-5 divide-y divide-zinc-100">
          {(allowedUsers.data ?? []).map((user) => (
            <div key={user.id} className="flex items-center justify-between gap-3 py-3">
              <div>
                <p className="font-medium text-zinc-950">{user.display_name || user.username || user.phone_number || "Telegram user"}</p>
                <p className="text-sm text-zinc-500">
                  {user.username ? `@${user.username}` : ""} {user.phone_number ?? ""} {user.user_id ? `linked ${user.user_id}` : ""}
                </p>
                <div className="mt-2 flex gap-2">
                  {user.can_ingest ? <Badge tone="green">Ingest</Badge> : null}
                  {user.can_query ? <Badge tone="blue">Ask</Badge> : null}
                </div>
              </div>
              <Button variant="ghost" size="icon" onClick={() => removeAllowedUser(user)}>
                <Trash2 className="h-4 w-4" aria-hidden />
              </Button>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function Notifications() {
  const notifications = useQuery({ queryKey: ["notifications"], queryFn: () => api<Array<Record<string, unknown>>>("/notifications") });
  return (
    <Panel className="p-5">
      <h3 className="flex items-center gap-2 font-semibold text-zinc-950">
        <Bell className="h-5 w-5 text-amber-700" aria-hidden />
        Notifications
      </h3>
      <div className="mt-4 divide-y divide-zinc-100">
        {(notifications.data ?? []).map((notification) => (
          <div key={String(notification.id)} className="py-3">
            <p className="font-medium text-zinc-950">{String(notification.title)}</p>
            <p className="text-sm text-zinc-500">{String(notification.body)}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function SecuritySettings() {
  return (
    <Panel className="p-5">
      <h3 className="flex items-center gap-2 font-semibold text-zinc-950">
        <ShieldCheck className="h-5 w-5 text-emerald-700" aria-hidden />
        Security posture
      </h3>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {[
          "HTTP-only JWT session cookies",
          "Tenant-scoped API dependencies",
          "Encrypted provider API keys",
          "Backend-mediated S3 uploads",
          "Prompt injection aware grounding",
          "Audit logs for sensitive actions",
        ].map((item) => (
          <div key={item} className="rounded-md bg-zinc-50 p-3 text-sm text-zinc-700">
            {item}
          </div>
        ))}
      </div>
    </Panel>
  );
}

function AuditLogs() {
  const logs = useQuery({ queryKey: ["audit-logs"], queryFn: () => api<Array<Record<string, unknown>>>("/audit-logs") });
  return (
    <Panel className="overflow-hidden">
      <div className="border-b border-zinc-200 px-4 py-3">
        <h3 className="font-semibold text-zinc-950">Audit Logs</h3>
      </div>
      <div className="divide-y divide-zinc-100">
        {(logs.data ?? []).map((log) => (
          <div key={String(log.id)} className="grid gap-2 px-4 py-3 lg:grid-cols-[180px_1fr_180px]">
            <span className="text-sm text-zinc-500">{shortDate(String(log.created_at))}</span>
            <span className="font-medium text-zinc-950">{String(log.action)}</span>
            <span className="text-sm text-zinc-500">{String(log.resource_type)}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
