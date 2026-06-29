from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def utcnow() -> datetime:
    return datetime.now(UTC)


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_secret(value: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def verify_secret(value: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_secret(value), hashed)


def create_session_token(user_id: UUID, organization_id: UUID | None, role: str | None) -> str:
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org": str(organization_id) if organization_id else None,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.session_ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_session_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def encrypt_secret(value: str) -> str:
    return Fernet(settings.encryption_key.encode()).encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return Fernet(settings.encryption_key.encode()).decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Secret could not be decrypted") from exc


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
