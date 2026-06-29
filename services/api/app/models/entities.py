from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MemberRole(StrEnum):
    OWNER = "Owner"
    ADMIN = "Admin"
    EDITOR = "Editor"
    MEMBER = "Member"
    VIEWER = "Viewer"


class ConfidentialityLevel(StrEnum):
    PUBLIC = "Public"
    INTERNAL = "Internal"
    CONFIDENTIAL = "Confidential"
    RESTRICTED = "Restricted"


class DocumentStatus(StrEnum):
    DRAFT = "DRAFT"
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    EXTRACTING = "EXTRACTING"
    QUALITY_ANALYSIS = "QUALITY_ANALYSIS"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    CLEANING = "CLEANING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DELETED = "DELETED"


class PipelineStage(StrEnum):
    DRAFT = "DRAFT"
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    EXTRACTING = "EXTRACTING"
    QUALITY_ANALYSIS = "QUALITY_ANALYSIS"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    CLEANING = "CLEANING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProviderKind(StrEnum):
    OPENAI = "OpenAI"
    ANTHROPIC = "Anthropic"
    GEMINI = "Google Gemini"
    XAI = "xAI Grok"
    LOCAL = "Local"


class ProfileKind(StrEnum):
    CHAT = "chat"
    EMBEDDING = "embedding"
    RERANKER = "reranker"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200))
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[OrganizationMember]] = relationship(back_populates="user")


class Organization(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False)
    retention_days: Mapped[int | None] = mapped_column(Integer)
    kms_key_alias: Mapped[str | None] = mapped_column(String(255))
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    members: Mapped[list[OrganizationMember]] = relationship(back_populates="organization")


class OrganizationMember(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MemberRole] = mapped_column(Enum(MemberRole), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class OrganizationInvitation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "organization_invitations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    role: Mapped[MemberRole] = mapped_column(Enum(MemberRole), default=MemberRole.MEMBER)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OTPCode(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "otp_codes"

    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), default="login", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    request_ip: Mapped[str | None] = mapped_column(String(64))


class Session(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(64))


class ProviderConnection(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "provider_connections"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    provider: Mapped[ProviderKind] = mapped_column(Enum(ProviderKind), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    masked_api_key: Mapped[str | None] = mapped_column(String(32))
    base_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(40), default="untested", nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class TelegramIntegration(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "telegram_integrations"
    __table_args__ = (UniqueConstraint("organization_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    encrypted_bot_token: Mapped[str | None] = mapped_column(Text)
    masked_bot_token: Mapped[str | None] = mapped_column(String(32))
    bot_username: Mapped[str | None] = mapped_column(String(160))
    webhook_secret_token: Mapped[str] = mapped_column(String(160), nullable=False)
    default_knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id"))
    default_chat_model_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("model_profiles.id"))
    default_cleanup_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cleanup_profiles.id"))
    default_chunking_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("chunking_profiles.id"))
    default_embedding_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("embedding_profiles.id"))
    auto_ingest_text: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_ingest_documents: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_ingest_voice: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class TelegramAllowedUser(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "telegram_allowed_users"
    __table_args__ = (
        UniqueConstraint("integration_id", "telegram_user_id"),
        UniqueConstraint("integration_id", "username"),
        UniqueConstraint("integration_id", "phone_number"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    integration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("telegram_integrations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    username: Mapped[str | None] = mapped_column(String(160))
    phone_number: Mapped[str | None] = mapped_column(String(40))
    display_name: Mapped[str | None] = mapped_column(String(220))
    can_ingest: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_query: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ModelProfile(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "model_profiles"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    provider_connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("provider_connections.id"))
    kind: Mapped[ProfileKind] = mapped_column(Enum(ProfileKind), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_embeddings: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_structured_output: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    context_window: Mapped[int | None] = mapped_column(Integer)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CleanupProfile(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "cleanup_profiles"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    strategy: Mapped[str] = mapped_column(String(80), nullable=False)
    use_for_retrieval: Mapped[str] = mapped_column(String(40), default="cleaned", nullable=False)
    pause_on_quality_issues: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ChunkingProfile(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "chunking_profiles"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    strategy: Mapped[str] = mapped_column(String(80), nullable=False)
    chunk_size_tokens: Mapped[int] = mapped_column(Integer, default=850, nullable=False)
    overlap_tokens: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class EmbeddingProfile(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "embedding_profiles"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    provider_connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("provider_connections.id"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider: Mapped[ProviderKind] = mapped_column(Enum(ProviderKind), default=ProviderKind.LOCAL, nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), default="deterministic-local-384", nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, default=384, nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, default=64, nullable=False)
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer)
    normalization: Mapped[str] = mapped_column(String(40), default="l2", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class KnowledgeBase(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "knowledge_bases"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    default_cleanup_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cleanup_profiles.id"))
    default_chunking_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("chunking_profiles.id"))
    default_embedding_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("embedding_profiles.id"))
    default_retrieval_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    confidentiality: Mapped[ConfidentialityLevel] = mapped_column(
        Enum(ConfidentialityLevel), default=ConfidentialityLevel.INTERNAL, nullable=False
    )
    retention_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    access_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class Category(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "categories"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id"), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    path: Mapped[str] = mapped_column(String(1200), nullable=False)
    access_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class Document(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id"), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(40), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    s3_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    business_unit: Mapped[str | None] = mapped_column(String(160))
    confidentiality: Mapped[ConfidentialityLevel] = mapped_column(
        Enum(ConfidentialityLevel), default=ConfidentialityLevel.INTERNAL, nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    processing_status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.DRAFT, nullable=False
    )
    access_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    custom_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class DocumentVersion(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_number"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    s3_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64))
    file_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DocumentAccessRule(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "document_access_rules"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), index=True)
    principal_type: Mapped[str] = mapped_column(String(40), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(160), nullable=False)
    permission: Mapped[str] = mapped_column(String(40), default="read", nullable=False)


class DocumentQualityReport(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "document_quality_reports"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="ok", nullable=False)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)


class DerivedDocumentContent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "derived_document_content"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), default="pipeline", nullable=False)
    source_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Chunk(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_org_kb_doc", "organization_id", "knowledge_base_id", "document_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("chunks.id"))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    sheet_name: Mapped[str | None] = mapped_column(String(160))
    heading_hierarchy: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    confidentiality: Mapped[ConfidentialityLevel] = mapped_column(Enum(ConfidentialityLevel), nullable=False)
    access_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    chunking_strategy: Mapped[str] = mapped_column(String(80), nullable=False)
    chunking_configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class EmbeddingVector(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "embedding_vectors"
    __table_args__ = (
        UniqueConstraint("chunk_id", "embedding_profile_id"),
        Index("ix_embedding_vectors_org_kb", "organization_id", "knowledge_base_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), index=True)
    embedding_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("embedding_profiles.id"), index=True)
    embedding_model: Mapped[str] = mapped_column(String(160), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)


class PipelineRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "pipeline_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id"), index=True)
    cleanup_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cleanup_profiles.id"))
    chunking_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("chunking_profiles.id"))
    embedding_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("embedding_profiles.id"))
    retrieval_index_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    current_stage: Mapped[PipelineStage] = mapped_column(Enum(PipelineStage), default=PipelineStage.QUEUED, nullable=False)
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_item: Mapped[str | None] = mapped_column(Text)
    processed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_completion_seconds: Mapped[int | None] = mapped_column(Integer)
    estimated_completion_confidence: Mapped[str] = mapped_column(String(40), default="Low", nullable=False)
    actual_completion_seconds: Mapped[int | None] = mapped_column(Integer)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    worker_logs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PipelineRunDocument(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "pipeline_run_documents"
    __table_args__ = (UniqueConstraint("pipeline_run_id", "document_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    status: Mapped[PipelineStage] = mapped_column(Enum(PipelineStage), default=PipelineStage.QUEUED, nullable=False)
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)


class PipelineTask(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "pipeline_tasks"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True)
    task_name: Mapped[str] = mapped_column(String(120), nullable=False)
    stage: Mapped[PipelineStage] = mapped_column(Enum(PipelineStage), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued", nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatSession(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "chat_sessions"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="New chat", nullable=False)
    knowledge_base_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    retrieval_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    model_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("model_profiles.id"))


class ChatMessage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    chat_session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class RetrievalEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "retrieval_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    chat_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"))
    original_query: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_query: Mapped[str | None] = mapped_column(Text)
    applied_filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    vector_candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    keyword_candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    rrf_ranking: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    reranker_scores: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    final_context_chunks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    token_usage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    latency_ms_by_stage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class TelegramMessageLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "telegram_message_logs"
    __table_args__ = (
        UniqueConstraint("integration_id", "telegram_chat_id", "telegram_message_id"),
        Index("ix_telegram_logs_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    integration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("telegram_integrations.id", ondelete="CASCADE"), index=True)
    telegram_chat_id: Mapped[str] = mapped_column(String(80), nullable=False)
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    mode: Mapped[str] = mapped_column(String(40), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="received", nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"))
    error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class Notification(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "notifications"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="info", nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class NotificationPreference(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", "kind"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AuditLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(120))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class UsageMetric(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "usage_metrics"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    metric_name: Mapped[str] = mapped_column(String(120), nullable=False)
    metric_value: Mapped[float] = mapped_column(Numeric, nullable=False)
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


Index("ix_documents_org_checksum", Document.organization_id, Document.checksum)
Index("ix_chat_messages_session_created", ChatMessage.chat_session_id, ChatMessage.created_at)
Index("ix_audit_logs_org_created", AuditLog.organization_id, AuditLog.created_at)
