import type {
  ChatMessage,
  DocumentRecord,
  KnowledgeBase,
  Organization,
  PipelineRun,
  Role,
  User,
} from "@rag-console/shared-types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export interface AuthResponse {
  user?: User | null;
  organization?: Organization | null;
  role?: Role | null;
  needs_onboarding: boolean;
  dev_code?: string | null;
  message: string;
}

export interface Category {
  id: string;
  knowledge_base_id: string;
  parent_id?: string | null;
  name: string;
  path: string;
  access_policy: Record<string, unknown>;
}

export interface ProviderConnection {
  id: string;
  provider: string;
  name: string;
  masked_api_key?: string | null;
  base_url?: string | null;
  status: string;
  is_enabled: boolean;
  config: Record<string, unknown>;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init.headers,
    },
  });
  if (!response.ok) {
    let message = `Request failed with ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail ?? body.message ?? message;
    } catch {
      // Keep the status-based message.
    }
    throw new Error(message);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function getMe() {
  return api<AuthResponse>("/auth/me");
}

export function listKnowledgeBases() {
  return api<KnowledgeBase[]>("/knowledge-bases");
}

export function listDocuments(knowledgeBaseId?: string) {
  const qs = knowledgeBaseId ? `?knowledge_base_id=${knowledgeBaseId}` : "";
  return api<DocumentRecord[]>(`/documents${qs}`);
}

export function listPipelineRuns() {
  return api<PipelineRun[]>("/pipeline-runs");
}

export function getPipelineRun(id: string) {
  return api<PipelineRun>(`/pipeline-runs/${id}`);
}

export function listChatSessions() {
  return api<Array<{ id: string; title: string; knowledge_base_ids: string[]; retrieval_config: Record<string, unknown> }>>(
    "/chat-sessions",
  );
}

export function getChatSession(id: string) {
  return api<{ session: unknown; messages: ChatMessage[] }>(`/chat-sessions/${id}`);
}
