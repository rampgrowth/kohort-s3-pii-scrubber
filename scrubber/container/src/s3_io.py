"""S3 read/write helpers."""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote, urlparse

import boto3

_s3 = boto3.client("s3")


def normalize_batch_object_key(key: str) -> str:
    """Decode URL-encoded keys from S3 Batch Operations Lambda invoke events."""
    if "%" not in key:
        return key
    return unquote(key)


def parse_bucket_arn(bucket_arn: str) -> str:
    # arn:aws:s3:::my-bucket or arn:aws:s3:::my-bucket/key
    if bucket_arn.startswith("arn:"):
        parts = bucket_arn.split(":", 5)
        resource = parts[5] if len(parts) > 5 else ""
        return resource.split("/", 1)[0]
    return bucket_arn


def map_dest_key(source_key: str, source_prefix: str, dest_prefix: str) -> str:
    relative = source_key
    if source_prefix and source_key.startswith(source_prefix):
        relative = source_key[len(source_prefix) :]
    return f"{dest_prefix}{relative}" if dest_prefix else relative


def get_object(bucket: str, key: str) -> tuple[bytes, dict[str, Any]]:
    response = _s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read()
    metadata = {
        "content_type": response.get("ContentType"),
        "metadata": response.get("Metadata") or {},
        "sse": response.get("ServerSideEncryption"),
        "kms_key_id": response.get("SSEKMSKeyId"),
    }
    return body, metadata


def put_object(
    bucket: str,
    key: str,
    body: bytes,
    *,
    content_type: str | None = None,
    metadata: dict[str, str] | None = None,
    sse: str | None = None,
    kms_key_id: str | None = None,
) -> None:
    extra: dict[str, Any] = {}
    if content_type:
        extra["ContentType"] = content_type
    if metadata:
        extra["Metadata"] = metadata
    if sse:
        extra["ServerSideEncryption"] = sse
    if kms_key_id:
        extra["SSEKMSKeyId"] = kms_key_id

    _s3.put_object(Bucket=bucket, Key=key, Body=body, **extra)


def parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3":
        raise ValueError(f"Not an s3 URI: {uri}")
    return parsed.netloc, parsed.path.lstrip("/")
