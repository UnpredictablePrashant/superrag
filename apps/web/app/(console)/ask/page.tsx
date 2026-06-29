"use client";

import { ErrorBox } from "@/components/error-box";
import {
  API_URL,
  api,
  getChatSession,
  getWorkspaceSummary,
  listChatSessions,
  listConnectors,
  listKnowledgeBases,
  listProfiles,
  saveLiveResult,
} from "@/lib/api";
import type { AnswerMode, ChatMessage, Citation } from "@rag-console/shared-types";
import { Badge, Button, Panel, Select, Textarea } from "@rag-console/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  BookOpen,
  CheckCircle2,
  Database,
  Globe,
  MessageSquarePlus,
  Plug,
  Send,
  Square,
  Trash2,
} from "lucide-react";
import * as React from "react";

const answerModes: Array<{ id: AnswerMode; label: string; icon: typeof Database }> = [
  { id: "company_data", label: "Company data", icon: Database },
  { id: "live_web", label: "Live web", icon: Globe },
  { id: "mcp_tools", label: "MCP tools", icon: Plug },
  { id: "blended", label: "Blended", icon: CheckCircle2 },
];

export default function AskPage() {
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = React.useState("");
  const [prompt, setPrompt] = React.useState("");
  const [selectedKbIds, setSelectedKbIds] = React.useState<string[]>([]);
  const [selectedModelProfileId, setSelectedModelProfileId] = React.useState("");
  const [answerMode, setAnswerMode] = React.useState<AnswerMode>("company_data");
  const [selectedConnectorIds, setSelectedConnectorIds] = React.useState<string[]>([]);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = React.useState("");
  const [selectedCitation, setSelectedCitation] = React.useState<Citation | null>(null);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const streamRef = React.useRef<EventSource | null>(null);

  const summary = useQuery({ queryKey: ["workspace-summary"], queryFn: getWorkspaceSummary, refetchInterval: 10000 });
  const kbs = useQuery({ queryKey: ["knowledge-bases"], queryFn: listKnowledgeBases });
  const sessions = useQuery({ queryKey: ["chat-sessions"], queryFn: listChatSessions });
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: listProfiles });
  const connectors = useQuery({ queryKey: ["connectors"], queryFn: listConnectors });
  const activeSession = useQuery({
    queryKey: ["chat-session", sessionId],
    enabled: Boolean(sessionId),
    queryFn: () => getChatSession(sessionId),
  });

  React.useEffect(() => {
    if (!sessionId && sessions.data?.[0]) setSessionId(sessions.data[0].id);
  }, [sessionId, sessions.data]);
  React.useEffect(() => {
    if (activeSession.data?.messages) setMessages(activeSession.data.messages);
    const profileId = activeSession.data?.session.model_profile_id;
    if (profileId && profiles.data?.chat_profiles.some((profile) => profile.id === profileId)) {
      setSelectedModelProfileId(profileId);
    }
  }, [activeSession.data, profiles.data]);
  React.useEffect(() => {
    const defaultKbId = summary.data?.default_knowledge_base?.id ?? kbs.data?.[0]?.id;
    if (!selectedKbIds.length && defaultKbId) setSelectedKbIds([defaultKbId]);
  }, [kbs.data, selectedKbIds.length, summary.data?.default_knowledge_base?.id]);
  React.useEffect(() => {
    if (!selectedModelProfileId && profiles.data?.chat_profiles[0]) {
      setSelectedModelProfileId(profiles.data.chat_profiles[0].id);
    }
  }, [profiles.data, selectedModelProfileId]);
  React.useEffect(() => {
    const available = summary.data?.available_answer_modes ?? ["company_data"];
    if (!available.includes(answerMode)) setAnswerMode(available[0] ?? "company_data");
  }, [answerMode, summary.data?.available_answer_modes]);

  const createSession = useMutation({
    mutationFn: () =>
      api<{ id: string; title: string }>("/chat-sessions", {
        method: "POST",
        body: JSON.stringify({
          title: "New chat",
          knowledge_base_ids: selectedKbIds,
          model_profile_id: selectedModelProfileId || undefined,
        }),
      }),
    onSuccess: (session) => {
      setSessionId(session.id);
      setMessages([]);
      queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
    },
  });

  async function sendMessage() {
    if (!prompt.trim()) return;
    setError("");
    setNotice("");
    setStreamingText("");
    const modelProfileId = selectedModel ? selectedModelProfileId : "";
    try {
      let id = sessionId;
      if (!id) {
        const created = await api<{ id: string }>("/chat-sessions", {
          method: "POST",
          body: JSON.stringify({
            title: "New chat",
            knowledge_base_ids: selectedKbIds,
            model_profile_id: modelProfileId || undefined,
          }),
        });
        id = created.id;
        setSessionId(id);
      } else if (modelProfileId && activeSession.data?.session.model_profile_id !== modelProfileId) {
        await api(`/chat-sessions/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ model_profile_id: modelProfileId }),
        });
      }
      const turn = await api<{
        user_message: ChatMessage;
        assistant_message: ChatMessage;
        suggested_questions: string[];
      }>(`/chat-sessions/${id}/messages`, {
        method: "POST",
        body: JSON.stringify({
          content: prompt,
          knowledge_base_ids: selectedKbIds,
          answer_mode: answerMode,
          connector_connection_ids: selectedConnectorIds,
        }),
      });
      setMessages((current) => [...current, turn.user_message]);
      setPrompt("");
      streamRef.current?.close();
      const source = new EventSource(`${API_URL}/chat-sessions/${id}/stream?message_id=${turn.assistant_message.id}`, {
        withCredentials: true,
      });
      streamRef.current = source;
      source.addEventListener("token", (event) => {
        const payload = JSON.parse((event as MessageEvent).data) as { text: string };
        setStreamingText((current) => current + payload.text);
      });
      source.addEventListener("done", (event) => {
        const payload = JSON.parse((event as MessageEvent).data) as { content: string; citations: Citation[] };
        setMessages((current) => [
          ...current,
          { ...turn.assistant_message, content: payload.content, citations: payload.citations },
        ]);
        setStreamingText("");
        source.close();
        queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
      });
      source.onerror = () => {
        source.close();
        setMessages((current) => [...current, turn.assistant_message]);
        setStreamingText("");
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send message.");
    }
  }

  async function saveCitation(citation: Citation) {
    const kbId = selectedKbIds[0] ?? summary.data?.default_knowledge_base?.id;
    if (!kbId) {
      setError("Create a knowledge base before saving live evidence.");
      return;
    }
    try {
      await saveLiveResult({
        knowledge_base_id: kbId,
        title: citation.document_name,
        content: citation.preview,
        source_url: citation.source_url,
        source_type: citation.source_type ?? "live_mcp",
        confidentiality: "Internal",
        tags: ["live-evidence"],
        share_with_organization: true,
        custom_metadata: { chunk_id: citation.chunk_id },
      });
      setNotice("Saved to company data. Indexing has been queued.");
      queryClient.invalidateQueries({ queryKey: ["workspace-summary"] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save source.");
    }
  }

  function stopStream() {
    streamRef.current?.close();
    streamRef.current = null;
    setStreamingText("");
  }

  const selectedKbName = kbs.data?.filter((kb) => selectedKbIds.includes(kb.id)).map((kb) => kb.name).join(", ");
  const selectedModel = profiles.data?.chat_profiles.find((profile) => profile.id === selectedModelProfileId);
  const activeConnectors = (connectors.data ?? []).filter((connection) => connection.kind === "mcp" && connection.is_enabled);
  const modeConnectors = activeConnectors.filter((connection) =>
    answerMode === "live_web" ? connection.web_search_supported : true,
  );
  const availableModes = summary.data?.available_answer_modes ?? ["company_data"];
  function toggleConnector(id: string) {
    setSelectedConnectorIds((current) => (current.includes(id) ? current.filter((value) => value !== id) : [...current, id]));
  }

  return (
    <div className="grid h-[calc(100vh-112px)] min-h-[680px] gap-4 xl:grid-cols-[280px_1fr_360px]">
      <Panel className="flex min-h-0 flex-col overflow-hidden">
        <div className="border-b border-zinc-200 p-4">
          <Button className="w-full" onClick={() => createSession.mutate()}>
            <MessageSquarePlus className="h-4 w-4" aria-hidden />
            New chat
          </Button>
        </div>
        <div className="border-b border-zinc-100 p-4">
          <p className="text-xs font-medium uppercase text-zinc-500">Workspace readiness</p>
          <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
            <ReadinessStat label="Indexed" value={summary.data?.indexed_document_count ?? 0} />
            <ReadinessStat label="Sources" value={summary.data?.active_source_count ?? 0} />
          </div>
          {summary.data?.review_item_count ? (
            <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900">
              {summary.data.review_item_count} item(s) need review in Activity.
            </p>
          ) : null}
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-2">
          {(sessions.data ?? []).map((session) => (
            <button
              key={session.id}
              className={`w-full rounded-md px-3 py-2 text-left text-sm ${
                sessionId === session.id ? "bg-emerald-50 text-emerald-800" : "text-zinc-700 hover:bg-zinc-100"
              }`}
              onClick={() => setSessionId(session.id)}
            >
              {session.title}
            </button>
          ))}
        </div>
      </Panel>

      <Panel className="flex min-h-0 flex-col overflow-hidden">
        <div className="border-b border-zinc-200 px-5 py-4">
          <div className="flex flex-col justify-between gap-3 xl:flex-row xl:items-start">
            <div>
              <h2 className="text-lg font-semibold text-zinc-950">Ask company knowledge</h2>
              <p className="text-xs text-zinc-500">Sources: {selectedKbName || "None selected"}</p>
            </div>
            <Badge tone="blue">{selectedModel ? `${selectedModel.provider} / ${selectedModel.model_name}` : "Local fallback"}</Badge>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {answerModes.map((mode) => {
              const Icon = mode.icon;
              const disabled = !availableModes.includes(mode.id);
              return (
                <button
                  key={mode.id}
                  disabled={disabled}
                  className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium ${
                    answerMode === mode.id
                      ? "border-emerald-300 bg-emerald-50 text-emerald-900"
                      : "border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50"
                  } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
                  onClick={() => setAnswerMode(mode.id)}
                >
                  <Icon className="h-4 w-4" aria-hidden />
                  {mode.label}
                </button>
              );
            })}
          </div>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-auto bg-zinc-50 p-5">
          <ErrorBox message={error} />
          {notice ? <div className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</div> : null}
          {!messages.length && !streamingText ? (
            <div className="flex h-full items-center justify-center text-center">
              <div>
                <BookOpen className="mx-auto h-10 w-10 text-zinc-400" aria-hidden />
                <h3 className="mt-4 font-semibold text-zinc-950">Ask with visible source provenance</h3>
                <p className="mt-2 max-w-md text-sm text-zinc-500">
                  Choose a source mode, ask a question, and inspect the exact evidence behind each answer.
                </p>
              </div>
            </div>
          ) : null}
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} onCitation={setSelectedCitation} />
          ))}
          {streamingText ? (
            <div className="rounded-md bg-white p-4 shadow-sm">
              <p className="whitespace-pre-wrap text-sm leading-6 text-zinc-900">{streamingText}</p>
            </div>
          ) : null}
        </div>
        <div className="border-t border-zinc-200 p-4">
          <Textarea
            placeholder="Ask about policy, projects, customers, systems, or live tools"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") sendMessage();
            }}
          />
          <div className="mt-3 flex items-center justify-between gap-3">
            <span className="text-xs text-zinc-500">{modeLabel(answerMode)}</span>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={stopStream}>
                <Square className="h-4 w-4" aria-hidden />
                Stop
              </Button>
              <Button disabled={!prompt.trim()} onClick={sendMessage}>
                <Send className="h-4 w-4" aria-hidden />
                Send
              </Button>
            </div>
          </div>
        </div>
      </Panel>

      <Panel className="flex min-h-0 flex-col overflow-hidden">
        <div className="border-b border-zinc-200 p-4">
          <h3 className="font-semibold text-zinc-950">Answer controls</h3>
          <p className="mt-1 text-xs text-zinc-500">Narrow the answer surface before retrieval runs.</p>
        </div>
        <div className="min-h-0 flex-1 space-y-5 overflow-auto p-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-800">Knowledge base</label>
            <Select
              value={selectedKbIds[0] ?? ""}
              onChange={(event) => setSelectedKbIds(event.target.value ? [event.target.value] : [])}
            >
              {(kbs.data ?? []).map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-800">Model</label>
            <Select value={selectedModelProfileId} onChange={(event) => setSelectedModelProfileId(event.target.value)}>
              {!(profiles.data?.chat_profiles ?? []).length ? <option value="">Local fallback</option> : null}
              {(profiles.data?.chat_profiles ?? []).map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.provider} / {profile.model_name}
                </option>
              ))}
            </Select>
          </div>
          {answerMode !== "company_data" ? (
            <div className="space-y-3 rounded-md border border-zinc-200 p-3">
              <p className="text-sm font-medium text-zinc-800">Live connectors</p>
              {modeConnectors.length ? (
                modeConnectors.map((connection) => (
                  <label key={connection.id} className="flex items-center justify-between gap-3 text-sm text-zinc-700">
                    <span className="flex items-center gap-2">
                      <input type="checkbox" checked={selectedConnectorIds.includes(connection.id)} onChange={() => toggleConnector(connection.id)} />
                      {connection.name}
                    </span>
                    <Badge tone={connection.web_search_supported ? "blue" : "green"}>
                      {connection.web_search_supported ? "web" : "mcp"}
                    </Badge>
                  </label>
                ))
              ) : (
                <p className="text-sm text-zinc-500">No enabled connector supports this mode yet.</p>
              )}
            </div>
          ) : null}
          {selectedCitation ? (
            <div className="rounded-md border border-zinc-200 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h4 className="font-semibold text-zinc-950">Source [{selectedCitation.id}]</h4>
                <Button variant="ghost" size="icon" onClick={() => setSelectedCitation(null)}>
                  <Trash2 className="h-4 w-4" aria-hidden />
                </Button>
              </div>
              <p className="text-sm font-medium text-zinc-800">{selectedCitation.document_name}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Badge tone={sourceTone(selectedCitation.source_type)}>{selectedCitation.source_type ?? "Indexed KB"}</Badge>
                {selectedCitation.source_url ? (
                  <a className="break-all text-xs text-sky-700 hover:underline" href={selectedCitation.source_url} target="_blank" rel="noreferrer">
                    {selectedCitation.source_url}
                  </a>
                ) : null}
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-zinc-600">{selectedCitation.preview}</p>
              {selectedCitation.source_type !== "Indexed KB" ? (
                <Button className="mt-3 w-full" variant="secondary" onClick={() => saveCitation(selectedCitation)}>
                  <Archive className="h-4 w-4" aria-hidden />
                  Save to company data
                </Button>
              ) : null}
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-zinc-300 p-4 text-sm text-zinc-500">
              Select a citation to preview or save the source.
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}

function ReadinessStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md bg-zinc-50 px-3 py-2">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="text-lg font-semibold text-zinc-950">{value}</p>
    </div>
  );
}

function MessageBubble({ message, onCitation }: { message: ChatMessage; onCitation: (citation: Citation) => void }) {
  const isUser = message.role === "user";
  const groups = groupCitations(message.citations ?? []);
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-3xl rounded-md p-4 shadow-sm ${isUser ? "bg-emerald-700 text-white" : "bg-white text-zinc-900"}`}>
        <p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p>
        {!isUser && message.citations?.length ? (
          <div className="mt-4 space-y-3">
            {groups.map((group) => (
              <div key={group.label}>
                <p className="mb-2 text-xs font-medium uppercase text-zinc-500">{group.label}</p>
                <div className="flex flex-wrap gap-2">
                  {group.citations.map((citation) => (
                    <button
                      key={citation.chunk_id}
                      className="rounded border border-zinc-200 bg-zinc-50 px-2 py-1 text-left text-xs text-zinc-700 hover:border-emerald-300"
                      onClick={() => onCitation(citation)}
                    >
                      [{citation.id}] {citation.document_name}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : null}
        {!isUser && !message.citations?.length ? <p className="mt-3 text-xs text-zinc-500">No citations returned.</p> : null}
      </div>
    </div>
  );
}

function groupCitations(citations: Citation[]) {
  const order = ["Indexed KB", "Live Web", "MCP"];
  const buckets = new Map<string, Citation[]>();
  for (const citation of citations) {
    const label = citation.source_type ?? "Indexed KB";
    buckets.set(label, [...(buckets.get(label) ?? []), citation]);
  }
  return [...buckets.entries()]
    .sort(([a], [b]) => order.indexOf(a) - order.indexOf(b))
    .map(([label, group]) => ({ label, citations: group }));
}

function sourceTone(sourceType?: string | null) {
  if (sourceType === "Indexed KB") return "blue";
  if (sourceType === "Live Web") return "amber";
  return "green";
}

function modeLabel(mode: AnswerMode) {
  if (mode === "company_data") return "Using indexed company data only.";
  if (mode === "live_web") return "Using live web-capable MCP tools only.";
  if (mode === "mcp_tools") return "Using read-only MCP tools only.";
  return "Using indexed company data plus live tools.";
}
