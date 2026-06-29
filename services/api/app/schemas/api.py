from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.entities import ConfidentialityLevel, MemberRole, PipelineStage, ProviderKind


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class UserOut(APIModel):
    id: UUID
    email: EmailStr
    full_name: str | None = None
    is_email_verified: bool


class OrganizationOut(APIModel):
    id: UUID
    name: str
    slug: str
    settings: dict[str, Any] = {}


class MemberOut(APIModel):
    id: UUID
    user_id: UUID
    email: EmailStr | None = None
    role: MemberRole
    status: str
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


class MemberPatchIn(BaseModel):
    role: MemberRole | None = None
    status: Literal["active", "removed"] | None = None


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
    default_retrieval_config: dict[str, Any] | None = None


class KnowledgeBaseOut(APIModel):
    id: UUID
    name: str
    description: str | None
    tags: list[str]
    confidentiality: ConfidentialityLevel
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


class ProfileOut(APIModel):
    id: UUID
    name: str
    strategy: str | None = None
    model_name: str | None = None
    provider: ProviderKind | None = None
    config: dict[str, Any] = {}


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
