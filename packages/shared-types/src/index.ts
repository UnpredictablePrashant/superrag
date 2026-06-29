export type Role = "Owner" | "Admin" | "Editor" | "Member" | "Viewer";

export type Confidentiality = "Public" | "Internal" | "Confidential" | "Restricted";

export type PipelineStage =
  | "DRAFT"
  | "QUEUED"
  | "VALIDATING"
  | "EXTRACTING"
  | "QUALITY_ANALYSIS"
  | "AWAITING_REVIEW"
  | "CLEANING"
  | "CHUNKING"
  | "EMBEDDING"
  | "INDEXING"
  | "COMPLETED"
  | "COMPLETED_WITH_WARNINGS"
  | "FAILED"
  | "CANCELLED";

export interface User {
  id: string;
  email: string;
  full_name?: string | null;
  is_email_verified: boolean;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  settings: Record<string, unknown>;
}

export interface KnowledgeBase {
  id: string;
  name: string;
  description?: string | null;
  tags: string[];
  confidentiality: Confidentiality;
  default_retrieval_config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DocumentRecord {
  id: string;
  knowledge_base_id: string;
  category_id?: string | null;
  name: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  tags: string[];
  business_unit?: string | null;
  confidentiality: Confidentiality;
  source_url?: string | null;
  version_number: number;
  checksum?: string | null;
  processing_status: string;
  custom_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PipelineRun {
  id: string;
  knowledge_base_id: string;
  current_stage: PipelineStage;
  progress_percentage: number;
  current_item?: string | null;
  processed_count: number;
  total_count: number;
  estimated_completion_seconds?: number | null;
  estimated_completion_confidence: string;
  actual_completion_seconds?: number | null;
  warnings: Array<Record<string, unknown>>;
  errors: Array<Record<string, unknown>>;
  retry_count: number;
  worker_logs: Array<Record<string, unknown>>;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  documents: Array<Record<string, unknown>>;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations: Citation[];
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Citation {
  id: number;
  chunk_id: string;
  document_id: string;
  document_name: string;
  page_start?: number | null;
  page_end?: number | null;
  heading_hierarchy: string[];
  preview: string;
}
