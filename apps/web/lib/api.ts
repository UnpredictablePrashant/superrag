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

export interface ModelOption {
  provider_connection_id?: string | null;
  connection_name: string;
  provider: string;
  model: string;
  supports_chat: boolean;
  supports_streaming: boolean;
  supports_embeddings: boolean;
  supports_structured_output: boolean;
  maximum_context_window?: number | null;
  maximum_output_tokens?: number | null;
  embedding_dimension?: number | null;
  status: string;
}

export interface ChatProfile {
  id: string;
  name: string;
  model_name: string;
  provider_connection_id?: string | null;
  provider: string;
  connection_name?: string | null;
  supports_streaming: boolean;
  supports_structured_output: boolean;
  context_window?: number | null;
  max_output_tokens?: number | null;
  is_default: boolean;
  config: Record<string, unknown>;
}

export interface EmbeddingProfile {
  id: string;
  name: string;
  provider: string;
  provider_connection_id?: string | null;
  connection_name?: string | null;
  model_name: string;
  embedding_dimension: number;
  batch_size: number;
  rate_limit_per_minute?: number | null;
  normalization: string;
  is_active: boolean;
  config: Record<string, unknown>;
}

export interface ProfilesResponse {
  chat_profiles: ChatProfile[];
  cleanup_profiles: Array<Record<string, unknown>>;
  chunking_profiles: Array<Record<string, unknown>>;
  embedding_profiles: EmbeddingProfile[];
}

export interface TelegramIntegration {
  id: string;
  bot_username?: string | null;
  masked_bot_token?: string | null;
  webhook_secret_token: string;
  webhook_url: string;
  default_knowledge_base_id?: string | null;
  default_chat_model_profile_id?: string | null;
  default_cleanup_profile_id?: string | null;
  default_chunking_profile_id?: string | null;
  default_embedding_profile_id?: string | null;
  auto_ingest_text: boolean;
  auto_ingest_documents: boolean;
  auto_ingest_voice: boolean;
  is_enabled: boolean;
  config: Record<string, unknown>;
}

export interface TelegramAllowedUser {
  id: string;
  telegram_user_id?: number | null;
  username?: string | null;
  phone_number?: string | null;
  display_name?: string | null;
  user_id?: string | null;
  can_ingest: boolean;
  can_query: boolean;
  is_enabled: boolean;
  created_at: string;
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
  return api<
    Array<{
      id: string;
      title: string;
      knowledge_base_ids: string[];
      retrieval_config: Record<string, unknown>;
      model_profile_id?: string | null;
    }>
  >(
    "/chat-sessions",
  );
}

export function getChatSession(id: string) {
  return api<{ session: { model_profile_id?: string | null }; messages: ChatMessage[] }>(`/chat-sessions/${id}`);
}

export function listProfiles() {
  return api<ProfilesResponse>("/profiles");
}

export function listProviderModels(refresh = false) {
  return api<ModelOption[]>(`/provider-connections/models${refresh ? "?refresh=true" : ""}`);
}

export function getTelegramIntegration() {
  return api<TelegramIntegration>("/integrations/telegram");
}

export function listTelegramAllowedUsers() {
  return api<TelegramAllowedUser[]>("/integrations/telegram/allowed-users");
}
