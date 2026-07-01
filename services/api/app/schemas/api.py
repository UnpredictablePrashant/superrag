from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.entities import (
    ChatPresenceStatus,
    ConfidentialityLevel,
    MemberRole,
    PipelineStage,
    ProviderKind,
)


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, protected_namespaces=())


class UserOut(APIModel):
    id: UUID
    email: EmailStr
    full_name: str | None = None
    job_title: str | None = None
    department: str | None = None
    phone_number: str | None = None
    telegram_username: str | None = None
    location: str | None = None
    bio: str | None = None
    is_email_verified: bool


class UserProfilePatchIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    job_title: str | None = Field(default=None, max_length=160)
    department: str | None = Field(default=None, max_length=160)
    phone_number: str | None = Field(default=None, max_length=40)
    telegram_username: str | None = Field(default=None, max_length=160)
    location: str | None = Field(default=None, max_length=160)
    bio: str | None = Field(default=None, max_length=2000)


class OrganizationOut(APIModel):
    id: UUID
    name: str
    slug: str
    settings: dict[str, Any] = {}


class MemberOut(APIModel):
    id: UUID
    user_id: UUID
    email: EmailStr | None = None
    full_name: str | None = None
    phone_number: str | None = None
    telegram_username: str | None = None
    role: MemberRole
    status: str
    chat_status: ChatPresenceStatus = ChatPresenceStatus.OFFLINE
    status_message: str | None = None
    status_updated_at: datetime | None = None
    created_at: datetime


class RequestOTPIn(BaseModel):
    email: EmailStr


class VerifyOTPIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    organization_name: str | None = None
    invitation_token: str | None = None


class AuthResponse(APIModel):
    user: UserOut | None = None
    organization: OrganizationOut | None = None
    role: MemberRole | None = None
    needs_onboarding: bool = False
    dev_code: str | None = None
    message: str = "ok"


class OrganizationCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class OrganizationPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    settings: dict[str, Any] | None = None


class InvitationCreateIn(BaseModel):
    email: EmailStr
    role: MemberRole = MemberRole.MEMBER
    telegram_user_id: int | None = None
    telegram_username: str | None = None
    telegram_phone_number: str | None = None
    telegram_can_ingest: bool = True
    telegram_can_query: bool = True


class MemberPatchIn(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=200)
    phone_number: str | None = Field(default=None, max_length=40)
    telegram_username: str | None = Field(default=None, max_length=160)
    role: MemberRole | None = None
    status: Literal["active", "removed"] | None = None


class ChatPresencePatchIn(BaseModel):
    chat_status: ChatPresenceStatus
    status_message: str | None = Field(default=None, max_length=160)


class KnowledgeBaseCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str | None = None
    tags: list[str] = []
    confidentiality: ConfidentialityLevel = ConfidentialityLevel.INTERNAL


class KnowledgeBasePatchIn(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    confidentiality: ConfidentialityLevel | None = None
    default_cleanup_profile_id: UUID | None = None
    default_chunking_profile_id: UUID | None = None
    default_embedding_profile_id: UUID | None = None
    default_retrieval_config: dict[str, Any] | None = None


class KnowledgeBaseOut(APIModel):
    id: UUID
    name: str
    description: str | None
    tags: list[str]
    confidentiality: ConfidentialityLevel
    default_cleanup_profile_id: UUID | None
    default_chunking_profile_id: UUID | None
    default_embedding_profile_id: UUID | None
    default_retrieval_config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CategoryCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: UUID | None = None
    access_policy: dict[str, Any] = {}


class CategoryOut(APIModel):
    id: UUID
    knowledge_base_id: UUID
    parent_id: UUID | None
    name: str
    path: str
    access_policy: dict[str, Any]


class UploadPresignIn(BaseModel):
    filename: str
    content_type: str | None = None
    size_bytes: int = Field(gt=0)
    knowledge_base_id: UUID
    category_id: UUID | None = None
    tags: list[str] = []
    business_unit: str | None = None
    confidentiality: ConfidentialityLevel = ConfidentialityLevel.INTERNAL
    source_url: str | None = None
    custom_metadata: dict[str, Any] = {}


class UploadPresignOut(APIModel):
    document_id: UUID
    version_id: UUID
    object_key: str
    upload_url: str
    headers: dict[str, str]
    multipart: bool
    upload_id: str | None = None
    part_urls: list[dict[str, str | int]] | None = None


class UploadCompleteIn(BaseModel):
    document_id: UUID
    upload_id: str | None = None
    parts: list[dict[str, Any]] = []


class DocumentPatchIn(BaseModel):
    name: str | None = None
    category_id: UUID | None = None
    tags: list[str] | None = None
    business_unit: str | None = None
    confidentiality: ConfidentialityLevel | None = None
    access_policy: dict[str, Any] | None = None
    custom_metadata: dict[str, Any] | None = None


class DocumentOut(APIModel):
    id: UUID
    knowledge_base_id: UUID
    category_id: UUID | None
    name: str
    original_filename: str
    file_type: str
    file_size: int
    tags: list[str]
    business_unit: str | None
    confidentiality: ConfidentialityLevel
    source_url: str | None
    version_number: int
    checksum: str | None
    processing_status: str
    custom_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ReviewActionIn(BaseModel):
    action: Literal[
        "continue_unchanged",
        "apply_recommended_cleanup",
        "exclude_document",
        "manual_edit",
        "redact_sections",
        "change_cleanup_profile",
        "rerun",
    ]
    edited_text: str | None = None
    cleanup_profile_id: UUID | None = None
    redactions: list[dict[str, Any]] = []


class PipelineRunCreateIn(BaseModel):
    knowledge_base_id: UUID
    document_ids: list[UUID]
    cleanup_profile_id: UUID | None = None
    chunking_profile_id: UUID | None = None
    embedding_profile_id: UUID | None = None
    retrieval_index_config: dict[str, Any] = {}


class PipelineRunOut(APIModel):
    id: UUID
    knowledge_base_id: UUID
    current_stage: PipelineStage
    progress_percentage: int
    current_item: str | None
    processed_count: int
    total_count: int
    estimated_completion_seconds: int | None
    estimated_completion_confidence: str
    actual_completion_seconds: int | None
    warnings: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    retry_count: int
    worker_logs: list[dict[str, Any]]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    documents: list[dict[str, Any]] = []


class ProviderConnectionCreateIn(BaseModel):
    provider: ProviderKind
    name: str
    api_key: str | None = None
    base_url: str | None = None
    config: dict[str, Any] = {}


class ProviderConnectionPatchIn(BaseModel):
    name: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    is_enabled: bool | None = None
    config: dict[str, Any] | None = None


class ProviderConnectionOut(APIModel):
    id: UUID
    provider: ProviderKind
    name: str
    masked_api_key: str | None
    base_url: str | None
    status: str
    is_enabled: bool
    config: dict[str, Any]


class ConnectorConnectionCreateIn(BaseModel):
    kind: Literal["web", "mcp"]
    scope: Literal["user", "organization"] = "user"
    name: str = Field(min_length=1, max_length=160)
    secret: str | None = None
    base_url: str | None = None
    is_enabled: bool = True
    config: dict[str, Any] = {}


class ConnectorConnectionPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    secret: str | None = None
    base_url: str | None = None
    is_enabled: bool | None = None
    config: dict[str, Any] | None = None


class ConnectorConnectionOut(APIModel):
    id: UUID
    kind: str
    scope: str
    user_id: UUID | None
    name: str
    masked_secret: str | None
    base_url: str | None
    status: str
    is_enabled: bool
    config: dict[str, Any]
    last_synced_at: datetime | None
    sync_supported: bool = True
    live_tools_supported: bool = False
    web_search_supported: bool = False
    tool_count: int = 0
    last_sync_status: str | None = None
    indexed_item_count: int = 0
    created_at: datetime
    updated_at: datetime


class ConnectorSyncIn(BaseModel):
    knowledge_base_id: UUID
    cleanup_profile_id: UUID | None = None
    chunking_profile_id: UUID | None = None
    embedding_profile_id: UUID | None = None
    retrieval_index_config: dict[str, Any] = {}
    share_with_organization: bool = False
    options: dict[str, Any] = {}


class ConnectorRunOut(APIModel):
    id: UUID
    connector_connection_id: UUID
    requested_by_user_id: UUID | None
    status: str
    options: dict[str, Any]
    total_items: int
    processed_items: int
    error: str | None
    logs: list[dict[str, Any]]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ConnectorItemOut(APIModel):
    id: UUID
    connector_connection_id: UUID
    connector_run_id: UUID | None
    document_id: UUID | None
    external_id: str
    title: str
    source_url: str | None
    content_type: str | None
    checksum: str | None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime
    updated_at: datetime


class LiveResultSaveIn(BaseModel):
    knowledge_base_id: UUID
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    source_url: str | None = None
    source_type: str = "live_mcp"
    confidentiality: ConfidentialityLevel = ConfidentialityLevel.INTERNAL
    tags: list[str] = []
    share_with_organization: bool = False
    custom_metadata: dict[str, Any] = {}


class CompanyEvidenceOut(APIModel):
    id: UUID
    document_id: UUID | None
    connector_item_id: UUID | None
    field_name: str
    source_type: str
    source_url: str | None
    excerpt: str | None
    confidence: float | None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime


class CompanyProfileOut(APIModel):
    id: UUID
    name: str
    normalized_name: str
    website_url: str | None
    description: str | None
    industry: str | None
    headquarters: str | None
    finance_summary: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime
    updated_at: datetime


class CompanyProfileDetailOut(CompanyProfileOut):
    evidence: list[CompanyEvidenceOut] = []


class RelationshipRoleOut(APIModel):
    id: UUID
    relationship_entity_id: UUID
    role_name: str
    confidence: float | None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime


class RelationshipEvidenceOut(APIModel):
    id: UUID
    relationship_entity_id: UUID | None
    deal_id: UUID | None
    interaction_id: UUID | None
    action_item_id: UUID | None
    document_id: UUID | None
    connector_item_id: UUID | None
    field_name: str
    source_type: str
    source_url: str | None
    excerpt: str | None
    confidence: float | None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime


class RelationshipEntityOut(APIModel):
    id: UUID
    name: str
    normalized_name: str
    entity_type: str
    summary: str | None
    sector: str | None
    geography: str | None
    website_url: str | None
    relationship_owner_user_id: UUID | None
    last_interaction_at: datetime | None
    next_action_at: datetime | None
    confidence: float | None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime
    updated_at: datetime
    role_names: list[str] = []
    evidence_count: int = 0
    open_action_count: int = 0


class InteractionOut(APIModel):
    id: UUID
    title: str
    interaction_type: str
    occurred_at: datetime | None
    source_type: str
    source_url: str | None
    document_id: UUID | None
    connector_item_id: UUID | None
    summary: str | None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime
    updated_at: datetime
    participants: list[dict[str, Any]] = []


class DealOut(APIModel):
    id: UUID
    name: str
    deal_type: str
    stage: str
    company_entity_id: UUID | None
    relationship_owner_user_id: UUID | None
    amount: float | None
    currency: str | None
    expected_close_date: datetime | None
    summary: str | None
    confidence: float | None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime
    updated_at: datetime
    participants: list[dict[str, Any]] = []


class ActionItemOut(APIModel):
    id: UUID
    title: str
    description: str | None
    relationship_entity_id: UUID | None
    deal_id: UUID | None
    interaction_id: UUID | None
    owner_user_id: UUID | None
    due_at: datetime | None
    priority: str
    status: str
    source_type: str
    confidence: float | None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime
    updated_at: datetime
    entity_name: str | None = None
    deal_name: str | None = None


class ActionItemCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    relationship_entity_id: UUID | None = None
    deal_id: UUID | None = None
    interaction_id: UUID | None = None
    owner_user_id: UUID | None = None
    due_at: datetime | None = None
    priority: Literal["low", "medium", "high"] = "medium"


class ActionItemPatchIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    owner_user_id: UUID | None = None
    due_at: datetime | None = None
    priority: Literal["low", "medium", "high"] | None = None
    status: Literal["open", "done", "dismissed"] | None = None


class RelationshipEntityDetailOut(RelationshipEntityOut):
    roles: list[RelationshipRoleOut] = []
    evidence: list[RelationshipEvidenceOut] = []
    interactions: list[InteractionOut] = []
    deals: list[DealOut] = []
    action_items: list[ActionItemOut] = []


class RelationshipSummaryOut(BaseModel):
    entity_count: int
    client_count: int
    investor_count: int
    contact_count: int
    open_action_count: int
    overdue_action_count: int
    deal_count: int
    interaction_count: int
    review_count: int
    recent_interactions: list[InteractionOut]
    upcoming_actions: list[ActionItemOut]


class RelationshipRescanIn(BaseModel):
    document_ids: list[UUID] = []


class RelationshipRescanOut(BaseModel):
    entities: int
    interactions: int
    actions: int
    deals: int


class RelationshipScanRunOut(APIModel):
    id: UUID
    scan_type: str
    status: str
    options: dict[str, Any]
    total_count: int
    processed_count: int
    last_scanned_document_id: UUID | None
    result: dict[str, Any]
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    last_scanned_document_name: str | None = None


class RelationshipDeleteAllOut(BaseModel):
    deleted: dict[str, int]


class RelationshipWebDiscoveryIn(BaseModel):
    query: str | None = Field(default=None, max_length=2000)


class ProfileOut(APIModel):
    id: UUID
    name: str
    strategy: str | None = None
    model_name: str | None = None
    provider: ProviderKind | None = None
    config: dict[str, Any] = {}


class ModelProfileCreateIn(BaseModel):
    provider_connection_id: UUID | None = None
    name: str = Field(min_length=1, max_length=160)
    model_name: str = Field(min_length=1, max_length=160)
    supports_streaming: bool = True
    supports_structured_output: bool = False
    context_window: int | None = None
    max_output_tokens: int | None = None
    is_default: bool = False
    config: dict[str, Any] = {}


class ModelProfilePatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    is_default: bool | None = None
    is_enabled: bool | None = None
    config: dict[str, Any] | None = None


class EmbeddingProfileCreateIn(BaseModel):
    provider_connection_id: UUID | None = None
    name: str = Field(min_length=1, max_length=160)
    model_name: str = Field(min_length=1, max_length=160)
    embedding_dimension: int = Field(gt=0, le=4096)
    batch_size: int = Field(default=64, gt=0, le=2048)
    rate_limit_per_minute: int | None = Field(default=None, gt=0)
    normalization: str = "l2"
    is_active: bool = True
    config: dict[str, Any] = {}


class TelegramIntegrationPatchIn(BaseModel):
    bot_token: str | None = Field(default=None, min_length=20)
    bot_username: str | None = None
    default_knowledge_base_id: UUID | None = None
    default_chat_model_profile_id: UUID | None = None
    default_cleanup_profile_id: UUID | None = None
    default_chunking_profile_id: UUID | None = None
    default_embedding_profile_id: UUID | None = None
    auto_ingest_text: bool | None = None
    auto_ingest_documents: bool | None = None
    auto_ingest_voice: bool | None = None
    is_enabled: bool | None = None
    config: dict[str, Any] | None = None


class TelegramIntegrationOut(APIModel):
    id: UUID
    bot_username: str | None
    masked_bot_token: str | None
    webhook_secret_token: str
    webhook_url: str
    default_knowledge_base_id: UUID | None
    default_chat_model_profile_id: UUID | None
    default_cleanup_profile_id: UUID | None
    default_chunking_profile_id: UUID | None
    default_embedding_profile_id: UUID | None
    auto_ingest_text: bool
    auto_ingest_documents: bool
    auto_ingest_voice: bool
    is_enabled: bool
    config: dict[str, Any]


class TelegramAllowedUserCreateIn(BaseModel):
    telegram_user_id: int | None = None
    username: str | None = None
    phone_number: str | None = None
    display_name: str | None = None
    user_id: UUID | None = None
    can_ingest: bool = True
    can_query: bool = True


class TelegramAllowedUserPatchIn(BaseModel):
    telegram_user_id: int | None = None
    username: str | None = None
    phone_number: str | None = None
    display_name: str | None = None
    user_id: UUID | None = None
    can_ingest: bool | None = None
    can_query: bool | None = None
    is_enabled: bool | None = None


class TelegramAllowedUserOut(APIModel):
    id: UUID
    telegram_user_id: int | None
    username: str | None
    phone_number: str | None
    display_name: str | None
    user_id: UUID | None
    can_ingest: bool
    can_query: bool
    is_enabled: bool
    created_at: datetime


class TelegramMessageLogOut(APIModel):
    id: UUID
    telegram_chat_id: str
    telegram_message_id: int
    telegram_user_id: int | None
    mode: str
    source_type: str
    status: str
    document_id: UUID | None
    pipeline_run_id: UUID | None
    error: str | None
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ChatSessionCreateIn(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    title: str = "New chat"
    knowledge_base_ids: list[UUID] = []
    retrieval_config: dict[str, Any] = {}
    model_profile_id: UUID | None = None


class ChatSessionPatchIn(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    title: str | None = None
    knowledge_base_ids: list[UUID] | None = None
    retrieval_config: dict[str, Any] | None = None
    model_profile_id: UUID | None = None


class ChatSessionOut(APIModel):
    id: UUID
    title: str
    knowledge_base_ids: list[str]
    retrieval_config: dict[str, Any]
    model_profile_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ChatMessageCreateIn(BaseModel):
    content: str = Field(min_length=1)
    knowledge_base_ids: list[UUID] | None = None
    filters: dict[str, Any] = {}
    answer_mode: Literal["company_data", "live_web", "mcp_tools", "blended"] | None = None
    use_web_search: bool = False
    use_mcp_tools: bool = False
    output_format: Literal["chat", "docx", "pdf"] = "chat"
    connector_connection_ids: list[UUID] = []
    debug: bool = False


class ChatMessageOut(APIModel):
    id: UUID
    role: str
    content: str
    citations: list[dict[str, Any]]
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime


class ChatTurnOut(BaseModel):
    user_message: ChatMessageOut
    assistant_message: ChatMessageOut
    retrieval_event_id: UUID
    suggested_questions: list[str]


class TeamChatParticipantOut(APIModel):
    user_id: UUID
    email: EmailStr
    full_name: str | None = None
    role: str
    chat_status: ChatPresenceStatus = ChatPresenceStatus.OFFLINE
    status_message: str | None = None
    status_updated_at: datetime | None = None
    last_read_at: datetime | None = None


class TeamChatAttachmentOut(APIModel):
    id: str
    filename: str
    content_type: str | None = None
    size_bytes: int
    kind: Literal["attachment", "voice"] = "attachment"
    download_url: str


class TeamChatMessageCreateIn(BaseModel):
    content: str = Field(default="", max_length=8000)
    message_type: Literal["text", "attachment", "voice"] = "text"


class TeamChatMessagePatchIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class TeamChatMessageOut(APIModel):
    id: UUID
    conversation_id: UUID
    user_id: UUID
    email: EmailStr
    full_name: str | None = None
    content: str
    message_type: Literal["text", "attachment", "voice"] = "text"
    attachments: list[TeamChatAttachmentOut] = []
    edited_at: datetime | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TeamChatConversationCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    member_user_ids: list[UUID] = []


class TeamChatDirectCreateIn(BaseModel):
    user_id: UUID


class TeamChatParticipantsAddIn(BaseModel):
    user_ids: list[UUID] = Field(min_length=1, max_length=100)


class TeamChatConversationOut(APIModel):
    id: UUID
    kind: Literal["channel", "direct"]
    name: str | None
    description: str | None
    created_by_user_id: UUID
    is_public: bool = False
    is_default: bool = False
    is_archived: bool
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime
    participants: list[TeamChatParticipantOut]
    unread_count: int = 0
    latest_message: TeamChatMessageOut | None = None


class RetrievalSearchIn(BaseModel):
    query: str
    knowledge_base_ids: list[UUID] = []
    filters: dict[str, Any] = {}
    debug: bool = False


class NotificationOut(APIModel):
    id: UUID
    kind: str
    title: str
    body: str
    severity: str
    read_at: datetime | None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime


class AuditLogOut(APIModel):
    id: UUID
    actor_user_id: UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime


class AIUsageRollupOut(BaseModel):
    request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0


class AIUsageUserOut(AIUsageRollupOut):
    user_id: str
    email: EmailStr | None = None
    full_name: str | None = None


class AIUsageModelOut(AIUsageRollupOut):
    model_config = ConfigDict(protected_namespaces=())

    provider: str
    model: str
    model_profile_id: str | None = None
    pricing_source: str | None = None
    input_cost_per_1m: float = 0
    output_cost_per_1m: float = 0


class AIUsageEventOut(AIUsageRollupOut):
    created_at: datetime
    user_id: str
    email: EmailStr | None = None
    provider: str
    model: str


class AIUsageSummaryOut(BaseModel):
    days: int
    totals: AIUsageRollupOut
    by_user: list[AIUsageUserOut]
    by_model: list[AIUsageModelOut]
    recent_events: list[AIUsageEventOut]


class WorkspaceSummaryOut(BaseModel):
    organization: OrganizationOut | None = None
    document_count: int
    indexed_document_count: int
    knowledge_base_count: int
    active_source_count: int
    failed_sync_count: int
    review_item_count: int
    available_answer_modes: list[str]
    default_knowledge_base: dict[str, Any] | None = None
    default_chat_model: dict[str, Any] | None = None
    source_health: dict[str, int]
