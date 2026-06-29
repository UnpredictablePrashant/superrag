"use client";

import { ErrorBox } from "@/components/error-box";
import { API_URL, api, getChatSession, listChatSessions, listKnowledgeBases } from "@/lib/api";
import type { ChatMessage, Citation } from "@rag-console/shared-types";
import { Badge, Button, Panel, Select, Textarea } from "@rag-console/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Bug, MessageSquarePlus, RefreshCw, Send, Square, Trash2 } from "lucide-react";
import * as React from "react";

export default function ChatPage() {
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = React.useState("");
  const [prompt, setPrompt] = React.useState("");
  const [selectedKbIds, setSelectedKbIds] = React.useState<string[]>([]);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = React.useState("");
  const [selectedCitation, setSelectedCitation] = React.useState<Citation | null>(null);
  const [debug, setDebug] = React.useState(false);
  const [error, setError] = React.useState("");
  const streamRef = React.useRef<EventSource | null>(null);

  const kbs = useQuery({ queryKey: ["knowledge-bases"], queryFn: listKnowledgeBases });
  const sessions = useQuery({ queryKey: ["chat-sessions"], queryFn: listChatSessions });
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
  }, [activeSession.data]);
  React.useEffect(() => {
    if (!selectedKbIds.length && kbs.data?.[0]) setSelectedKbIds([kbs.data[0].id]);
  }, [kbs.data, selectedKbIds.length]);

  const createSession = useMutation({
    mutationFn: () =>
      api<{ id: string; title: string }>("/chat-sessions", {
        method: "POST",
        body: JSON.stringify({ title: "New chat", knowledge_base_ids: selectedKbIds }),
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
    setStreamingText("");
    try {
      let id = sessionId;
      if (!id) {
        const created = await api<{ id: string }>("/chat-sessions", {
          method: "POST",
          body: JSON.stringify({ title: "New chat", knowledge_base_ids: selectedKbIds }),
        });
        id = created.id;
        setSessionId(id);
      }
      const turn = await api<{
        user_message: ChatMessage;
        assistant_message: ChatMessage;
        suggested_questions: string[];
      }>(`/chat-sessions/${id}/messages`, {
        method: "POST",
        body: JSON.stringify({ content: prompt, knowledge_base_ids: selectedKbIds, debug }),
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

  function stopStream() {
    streamRef.current?.close();
    streamRef.current = null;
    setStreamingText("");
  }

  const selectedKbName = kbs.data?.filter((kb) => selectedKbIds.includes(kb.id)).map((kb) => kb.name).join(", ");

  return (
    <div className="grid h-[calc(100vh-112px)] min-h-[680px] gap-4 xl:grid-cols-[260px_1fr_340px]">
      <Panel className="flex min-h-0 flex-col overflow-hidden">
        <div className="border-b border-zinc-200 p-4">
          <Button className="w-full" onClick={() => createSession.mutate()}>
            <MessageSquarePlus className="h-4 w-4" aria-hidden />
            New chat
          </Button>
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
        <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-3">
          <div>
            <h2 className="font-semibold text-zinc-950">Grounded Chat</h2>
            <p className="text-xs text-zinc-500">Knowledge bases: {selectedKbName || "None selected"}</p>
          </div>
          <Badge tone="blue">Local grounded responder</Badge>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-auto bg-zinc-50 p-5">
          <ErrorBox message={error} />
          {!messages.length && !streamingText ? (
            <div className="flex h-full items-center justify-center text-center">
              <div>
                <BookOpen className="mx-auto h-10 w-10 text-zinc-400" aria-hidden />
                <h3 className="mt-4 font-semibold text-zinc-950">Ask a grounded question</h3>
                <p className="mt-2 max-w-md text-sm text-zinc-500">
                  Answers retrieve authorized chunks first and include citations for source review.
                </p>
              </div>
            </div>
          ) : null}
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} onCitation={setSelectedCitation} />
          ))}
          {streamingText ? (
            <div className="rounded-lg bg-white p-4 shadow-sm">
              <p className="whitespace-pre-wrap text-sm leading-6 text-zinc-900">{streamingText}</p>
            </div>
          ) : null}
        </div>
        <div className="border-t border-zinc-200 p-4">
          <Textarea
            placeholder="Ask a question about selected knowledge bases"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") sendMessage();
            }}
          />
          <div className="mt-3 flex items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-sm text-zinc-600">
              <input type="checkbox" checked={debug} onChange={(event) => setDebug(event.target.checked)} />
              <Bug className="h-4 w-4" aria-hidden />
              Debug
            </label>
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
          <h3 className="font-semibold text-zinc-950">Retrieval Controls</h3>
          <p className="mt-1 text-xs text-zinc-500">Filter the answer surface before retrieval runs.</p>
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
          <div className="rounded-md bg-zinc-50 p-3 text-sm text-zinc-600">
            <p className="font-medium text-zinc-950">Model</p>
            <p className="mt-1">Local grounded responder for demo mode. Provider adapters are configured in Settings.</p>
          </div>
          {selectedCitation ? (
            <div className="rounded-md border border-zinc-200 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h4 className="font-semibold text-zinc-950">Source [{selectedCitation.id}]</h4>
                <Button variant="ghost" size="icon" onClick={() => setSelectedCitation(null)}>
                  <Trash2 className="h-4 w-4" aria-hidden />
                </Button>
              </div>
              <p className="text-sm font-medium text-zinc-800">{selectedCitation.document_name}</p>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-zinc-600">{selectedCitation.preview}</p>
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-zinc-300 p-4 text-sm text-zinc-500">
              Select a citation to preview the source chunk.
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}

function MessageBubble({ message, onCitation }: { message: ChatMessage; onCitation: (citation: Citation) => void }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-3xl rounded-lg p-4 shadow-sm ${isUser ? "bg-emerald-700 text-white" : "bg-white text-zinc-900"}`}>
        <p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p>
        {!isUser && message.citations?.length ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {message.citations.map((citation) => (
              <button
                key={citation.chunk_id}
                className="rounded border border-zinc-200 bg-zinc-50 px-2 py-1 text-left text-xs text-zinc-700 hover:border-emerald-300"
                onClick={() => onCitation(citation)}
              >
                [{citation.id}] {citation.document_name}
              </button>
            ))}
          </div>
        ) : null}
        {!isUser && !message.citations?.length ? <p className="mt-3 text-xs text-zinc-500">No citations returned.</p> : null}
        {!isUser && message.metadata?.suggested_questions ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {(message.metadata.suggested_questions as string[]).map((question) => (
              <Badge key={question}>{question}</Badge>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
