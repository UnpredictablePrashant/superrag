import type {
  AnswerMode,
  ChatMessage,
  Confidentiality,
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

export interface EmbeddingProfileCreateInput {
  provider_connection_id?: string | null;
  name: string;
  model_name: string;
  embedding_dimension: number;
  batch_size?: number;
  rate_limit_per_minute?: number | null;
  normalization?: string;
  is_active?: boolean;
  config?: Record<string, unknown>;
}

export interface ProcessingProfile {
  id: string;
  name: string;
  strategy: string;
  use_for_retrieval?: string;
  pause_on_quality_issues?: boolean;
  chunk_size_tokens?: number;
  overlap_tokens?: number;
  config: Record<string, unknown>;
}

export interface ProfilesResponse {
  chat_profiles: ChatProfile[];
  cleanup_profiles: ProcessingProfile[];
  chunking_profiles: ProcessingProfile[];
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

export interface TelegramMessageLog {
  id: string;
  telegram_chat_id: string;
  telegram_message_id: number;
  telegram_user_id?: number | null;
  mode: string;
  source_type: string;
  status: string;
  document_id?: string | null;
  pipeline_run_id?: string | null;
  error?: string | null;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ConnectorConnection {
  id: string;
  kind: "web" | "mcp" | string;
  scope: "user" | "organization" | string;
  user_id?: string | null;
  name: string;
  masked_secret?: string | null;
  base_url?: string | null;
  status: string;
  is_enabled: boolean;
  config: Record<string, unknown>;
  last_synced_at?: string | null;
  sync_supported: boolean;
  live_tools_supported: boolean;
  web_search_supported: boolean;
  tool_count: number;
  last_sync_status?: string | null;
  indexed_item_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConnectorRun {
  id: string;
  connector_connection_id: string;
  requested_by_user_id?: string | null;
  status: string;
  options: Record<string, unknown>;
  total_items: number;
  processed_items: number;
  error?: string | null;
  logs: Array<Record<string, unknown>>;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
}

export interface ConnectorItem {
  id: string;
  connector_connection_id: string;
  connector_run_id?: string | null;
  document_id?: string | null;
  external_id: string;
  title: string;
  source_url?: string | null;
  content_type?: string | null;
  checksum?: string | null;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceSummary {
  organization?: Organization | null;
  document_count: number;
  indexed_document_count: number;
  knowledge_base_count: number;
  active_source_count: number;
  failed_sync_count: number;
  review_item_count: number;
  available_answer_modes: AnswerMode[];
  default_knowledge_base?: { id: string; name: string; confidentiality: string } | null;
  default_chat_model?: { id?: string | null; name: string; provider: string; model_name: string } | null;
  source_health: Record<string, number>;
}

export interface DocumentQualityReport {
  id?: string;
  issues: Array<Record<string, unknown>>;
  severity: string;
  requires_review: boolean;
  summary?: string | null;
  created_at?: string;
}

export interface CompanyEvidence {
  id: string;
  document_id?: string | null;
  connector_item_id?: string | null;
  field_name: string;
  source_type: string;
  source_url?: string | null;
  excerpt?: string | null;
  confidence?: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface CompanyProfile {
  id: string;
  name: string;
  normalized_name: string;
  website_url?: string | null;
  description?: string | null;
  industry?: string | null;
  headquarters?: string | null;
  finance_summary: Record<string, unknown>;
  metadata: Record<string, unknown>;
  evidence?: CompanyEvidence[];
  created_at: string;
  updated_at: string;
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

export function updateKnowledgeBase(
  id: string,
  payload: Partial<
    Pick<
      KnowledgeBase,
      | "name"
      | "description"
      | "tags"
      | "confidentiality"
      | "default_cleanup_profile_id"
      | "default_chunking_profile_id"
      | "default_embedding_profile_id"
      | "default_retrieval_config"
    >
  >,
) {
  return api<KnowledgeBase>(`/knowledge-bases/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function listDocuments(knowledgeBaseId?: string) {
  const qs = knowledgeBaseId ? `?knowledge_base_id=${knowledgeBaseId}` : "";
  return api<DocumentRecord[]>(`/documents${qs}`);
}

export interface DocumentPreview {
  kind?: string | null;
  text: string;
}

export interface DocumentPatchInput {
  name?: string | null;
  category_id?: string | null;
  tags?: string[] | null;
  business_unit?: string | null;
  confidentiality?: Confidentiality | null;
  access_policy?: Record<string, unknown> | null;
  custom_metadata?: Record<string, unknown> | null;
}

export function previewDocument(documentId: string, kind = "cleaned") {
  return api<DocumentPreview>(`/documents/${documentId}/preview?kind=${encodeURIComponent(kind)}`);
}

export function updateDocument(documentId: string, payload: DocumentPatchInput) {
  return api<DocumentRecord>(`/documents/${documentId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteDocument(documentId: string, hard = false) {
  return api<{ message: string }>(`/documents/${documentId}${hard ? "?hard=true" : ""}`, { method: "DELETE" });
}

export function replaceDocumentFile(documentId: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return api<DocumentRecord>(`/documents/${documentId}/replace`, {
    method: "POST",
    body: formData,
  });
}

export interface UploadDocumentInput {
  knowledge_base_id: string;
  category_id?: string | null;
  tags?: string[];
  business_unit?: string | null;
  confidentiality?: Confidentiality;
  source_url?: string | null;
  custom_metadata?: Record<string, unknown>;
}

export function uploadDocument(file: File, payload: UploadDocumentInput) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("knowledge_base_id", payload.knowledge_base_id);
  formData.append("tags", JSON.stringify(payload.tags ?? []));
  formData.append("custom_metadata", JSON.stringify(payload.custom_metadata ?? {}));
  if (payload.category_id) formData.append("category_id", payload.category_id);
  if (payload.business_unit) formData.append("business_unit", payload.business_unit);
  if (payload.confidentiality) formData.append("confidentiality", payload.confidentiality);
  if (payload.source_url) formData.append("source_url", payload.source_url);
  return api<DocumentRecord>("/uploads", {
    method: "POST",
    body: formData,
  });
}

export interface PipelineRunCreateInput {
  knowledge_base_id: string;
  document_ids: string[];
  cleanup_profile_id?: string | null;
  chunking_profile_id?: string | null;
  embedding_profile_id?: string | null;
  retrieval_index_config?: Record<string, unknown>;
}

export function createPipelineRun(payload: PipelineRunCreateInput) {
  return api<PipelineRun>("/pipeline-runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
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

export function deleteChatSession(id: string) {
  return api<{ message: string }>(`/chat-sessions/${id}`, { method: "DELETE" });
}

export function listProfiles() {
  return api<ProfilesResponse>("/profiles");
}

export function listProviderModels(refresh = false) {
  return api<ModelOption[]>(`/provider-connections/models${refresh ? "?refresh=true" : ""}`);
}

export function createEmbeddingProfile(payload: EmbeddingProfileCreateInput) {
  return api<{ id: string; message: string }>("/profiles/embeddings", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getTelegramIntegration() {
  return api<TelegramIntegration>("/integrations/telegram");
}

export function listTelegramAllowedUsers() {
  return api<TelegramAllowedUser[]>("/integrations/telegram/allowed-users");
}

export function listTelegramMessages() {
  return api<TelegramMessageLog[]>("/integrations/telegram/messages");
}

export function listMembers() {
  return api<
    Array<{
      id: string;
      user_id: string;
      email: string;
      role: Role;
      status: string;
      created_at: string;
    }>
  >("/organizations/members");
}

export function listConnectors() {
  return api<ConnectorConnection[]>("/connectors");
}

export function listConnectorRuns(connectionId: string) {
  return api<ConnectorRun[]>(`/connectors/${connectionId}/runs`);
}

export function listConnectorItems(connectionId: string) {
  return api<ConnectorItem[]>(`/connectors/${connectionId}/items`);
}

export function getWorkspaceSummary() {
  return api<WorkspaceSummary>("/workspace/summary");
}

export function getDocumentQualityReport(documentId: string) {
  return api<DocumentQualityReport>(`/documents/${documentId}/quality-report`);
}

export function reviewDocument(documentId: string, action: string, editedText?: string) {
  return api(`/documents/${documentId}/review-action`, {
    method: "POST",
    body: JSON.stringify({ action, edited_text: editedText }),
  });
}

export function saveLiveResult(payload: {
  knowledge_base_id: string;
  title: string;
  content: string;
  source_url?: string | null;
  source_type: string;
  confidentiality?: Confidentiality;
  tags?: string[];
  share_with_organization?: boolean;
  custom_metadata?: Record<string, unknown>;
}) {
  return api<DocumentRecord>("/connectors/live-results", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listCompanyProfiles(search?: string) {
  const qs = search ? `?search=${encodeURIComponent(search)}` : "";
  return api<CompanyProfile[]>(`/company-profiles${qs}`);
}

export function getCompanyProfile(id: string) {
  return api<CompanyProfile>(`/company-profiles/${id}`);
}
