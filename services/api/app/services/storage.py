from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import PurePosixPath

import boto3
from botocore.client import Config
from fastapi import HTTPException, status

from app.core.config import settings

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".csv",
    ".txt",
    ".md",
    ".markdown",
    ".html",
    ".htm",
    ".json",
    ".xml",
}


@dataclass(frozen=True)
class UploadTarget:
    object_key: str
    upload_url: str
    headers: dict[str, str]
    multipart: bool = False
    upload_id: str | None = None
    part_urls: list[dict[str, str | int]] | None = None


def _s3_client(endpoint_url: str | None = None):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def internal_s3_client():
    return _s3_client(settings.s3_endpoint_url)


def public_s3_client():
    return _s3_client(settings.s3_public_endpoint_url)


def ensure_bucket() -> None:
    client = internal_s3_client()
    buckets = client.list_buckets().get("Buckets", [])
    if not any(bucket["Name"] == settings.s3_bucket for bucket in buckets):
        client.create_bucket(Bucket=settings.s3_bucket)


def validate_upload(filename: str, content_type: str | None, size_bytes: int) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unsupported file type.")
    if size_bytes > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload is too large.")
    guessed, _ = mimetypes.guess_type(filename)
    if content_type and guessed and content_type not in {guessed, "application/octet-stream"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="MIME type does not match filename.")
    return suffix.lstrip(".")


def build_object_key(
    organization_id: str,
    knowledge_base_id: str,
    document_id: str,
    version_id: str,
    filename: str,
) -> str:
    safe_filename = PurePosixPath(filename).name.replace("\\", "_").replace("/", "_")
    return (
        f"organizations/{organization_id}/knowledge-bases/{knowledge_base_id}/"
        f"documents/{document_id}/versions/{version_id}/original/{safe_filename}"
    )


def create_presigned_put(object_key: str, content_type: str | None) -> UploadTarget:
    client = public_s3_client()
    params: dict[str, str] = {"Bucket": settings.s3_bucket, "Key": object_key}
    headers: dict[str, str] = {}
    if content_type:
        params["ContentType"] = content_type
        headers["Content-Type"] = content_type
    upload_url = client.generate_presigned_url(
        "put_object",
        Params=params,
        ExpiresIn=60 * 30,
        HttpMethod="PUT",
    )
    return UploadTarget(object_key=object_key, upload_url=upload_url, headers=headers)


def create_multipart_presigned_urls(
    object_key: str, content_type: str | None, size_bytes: int
) -> UploadTarget:
    internal = internal_s3_client()
    public = public_s3_client()
    create_params: dict[str, str] = {"Bucket": settings.s3_bucket, "Key": object_key}
    if content_type:
        create_params["ContentType"] = content_type
    upload = internal.create_multipart_upload(**create_params)
    upload_id = upload["UploadId"]
    part_size = 10 * 1024 * 1024
    part_count = max(1, (size_bytes + part_size - 1) // part_size)
    part_urls = [
        {
            "part_number": part_number,
            "url": public.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": settings.s3_bucket,
                    "Key": object_key,
                    "UploadId": upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=60 * 30,
                HttpMethod="PUT",
            ),
        }
        for part_number in range(1, part_count + 1)
    ]
    return UploadTarget(
        object_key=object_key,
        upload_url="",
        headers={"Content-Type": content_type or "application/octet-stream"},
        multipart=True,
        upload_id=upload_id,
        part_urls=part_urls,
    )


def get_object_bytes(object_key: str) -> bytes:
    response = internal_s3_client().get_object(Bucket=settings.s3_bucket, Key=object_key)
    return response["Body"].read()


def put_object_bytes(object_key: str, data: bytes, content_type: str | None = None) -> None:
    params: dict[str, object] = {"Bucket": settings.s3_bucket, "Key": object_key, "Body": data}
    if content_type:
        params["ContentType"] = content_type
    internal_s3_client().put_object(**params)


def head_object(object_key: str) -> dict:
    return internal_s3_client().head_object(Bucket=settings.s3_bucket, Key=object_key)


def delete_object(object_key: str) -> None:
    internal_s3_client().delete_object(Bucket=settings.s3_bucket, Key=object_key)
