import pytest
from fastapi import HTTPException

from app.services.storage import build_object_key, validate_upload


def test_s3_object_key_is_tenant_scoped_and_sanitized() -> None:
    key = build_object_key("org", "kb", "doc", "ver", "../Handbook.md")
    assert key == "organizations/org/knowledge-bases/kb/documents/doc/versions/ver/original/Handbook.md"


def test_upload_validation_rejects_unsupported_extension() -> None:
    with pytest.raises(HTTPException):
        validate_upload("malware.exe", "application/octet-stream", 10)


def test_upload_validation_accepts_markdown() -> None:
    assert validate_upload("handbook.md", "text/markdown", 10) == "md"
