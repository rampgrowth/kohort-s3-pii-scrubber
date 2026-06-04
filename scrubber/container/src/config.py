"""Runtime configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    dest_bucket: str
    dest_prefix: str
    source_prefix: str
    ruleset_uri: str


def load_config() -> AppConfig:
    dest_bucket = os.environ.get("DEST_BUCKET", "").strip()
    ruleset_uri = os.environ.get("RULESET_URI", "").strip()
    if not dest_bucket:
        raise ValueError("DEST_BUCKET environment variable is required")
    if not ruleset_uri:
        raise ValueError("RULESET_URI environment variable is required")
    if not ruleset_uri.startswith("s3://"):
        raise ValueError("RULESET_URI must be an s3:// URI")

    return AppConfig(
        dest_bucket=dest_bucket,
        dest_prefix=_normalize_prefix(os.environ.get("DEST_PREFIX", "")),
        source_prefix=_normalize_prefix(os.environ.get("SOURCE_PREFIX", "")),
        ruleset_uri=ruleset_uri,
    )


def _normalize_prefix(prefix: str) -> str:
    if not prefix:
        return ""
    return prefix if prefix.endswith("/") else f"{prefix}/"
