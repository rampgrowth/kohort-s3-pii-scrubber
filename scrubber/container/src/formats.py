"""Detect object format from S3 key."""

from __future__ import annotations

from enum import Enum


class ObjectFormat(str, Enum):
    CSV = "csv"
    PARQUET = "parquet"


def detect_format(key: str) -> ObjectFormat | None:
    lower = key.lower()
    # .gz.parquet must be classified as Parquet (not gzip CSV).
    if lower.endswith(".parquet"):
        return ObjectFormat.PARQUET
    if lower.endswith(".csv.gz") or lower.endswith(".csv"):
        return ObjectFormat.CSV
    if lower.endswith(".gz"):
        return ObjectFormat.CSV
    return None
