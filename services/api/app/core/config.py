from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RAG Console"
    app_env: Literal["local", "test", "production"] = "local"
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg2://rag:rag@localhost:5432/rag_console"
    redis_url: str = "redis://localhost:6379/0"
    kafka_enabled: bool = False
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_pipeline_topic: str = "rag.pipeline-runs"
    kafka_pipeline_consumer_group: str = "rag-pipeline-workers"
    kafka_fallback_to_celery: bool = True
    jwt_secret: str = Field(default="dev-only-change-me", min_length=16)
    session_cookie_name: str = "rag_console_session"
    session_ttl_minutes: int = 60 * 24 * 7
    otp_ttl_minutes: int = 10
    otp_resend_cooldown_seconds: int = 45
    otp_max_attempts: int = 5
    allow_dev_auth_codes: bool = True
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "rag-console"
    s3_region: str = "us-east-1"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin"
    max_upload_bytes: int = 100 * 1024 * 1024
    multipart_threshold_bytes: int = 25 * 1024 * 1024

    email_backend: Literal["smtp", "ses", "console"] = "smtp"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    email_from: str = "RAG Console <no-reply@rag-console.local>"
    aws_region: str = "us-east-1"

    encryption_key: str = "Lh-eo7nR2y6f5jS1q41MTHeJ0P1Uo-4fAVoDIbHZVwU="
    deterministic_embedding_dimension: int = 384
    enable_dev_embedding_provider: bool = True
    enable_llm_content_processing: bool = False
    rate_limit_per_minute: int = 120
    connector_max_pages: int = 10
    connector_request_timeout_seconds: int = 20
    mcp_stdio_allowlist: str = ""

    @property
    def mcp_stdio_allowlist_values(self) -> list[str]:
        return [value.strip() for value in self.mcp_stdio_allowlist.split(",") if value.strip()]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        value = self.cors_origins.strip()
        if not value:
            return []
        if value.startswith("["):
            decoded = json.loads(value)
            if not isinstance(decoded, list):
                raise ValueError("CORS_ORIGINS JSON value must be an array.")
            return [str(origin).strip() for origin in decoded if str(origin).strip()]
        return [origin.strip() for origin in value.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
