"""Orchestrate scrubbing for a single S3 object."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from config import AppConfig
from csv_scrub import scrub_csv
from formats import ObjectFormat, detect_format
from parquet_scrub import scrub_parquet
from rules import Ruleset, drop_columns_for_key, get_ruleset, should_process
from s3_io import get_object, map_dest_key, put_object

logger = logging.getLogger(__name__)


@dataclass
class ScrubResult:
    source_bucket: str
    source_key: str
    dest_key: str
    format: str
    bytes_in: int
    bytes_out: int
    duration_ms: int
    skipped: bool = False


def scrub_object(
    config: AppConfig,
    ruleset: Ruleset,
    source_bucket: str,
    source_key: str,
) -> ScrubResult:
    start = time.perf_counter()

    if not should_process(ruleset, source_key):
        logger.info(
            "skipped_by_rules",
            extra={"source_key": source_key, "reason": "include/exclude globs"},
        )
        return ScrubResult(
            source_bucket=source_bucket,
            source_key=source_key,
            dest_key="",
            format="skipped",
            bytes_in=0,
            bytes_out=0,
            duration_ms=int((time.perf_counter() - start) * 1000),
            skipped=True,
        )

    fmt = detect_format(source_key)
    if fmt is None:
        raise ValueError(f"Unsupported file extension for key: {source_key}")

    drop_cols = drop_columns_for_key(ruleset, source_key)
    raw, meta = get_object(source_bucket, source_key)
    bytes_in = len(raw)

    if fmt == ObjectFormat.CSV:
        out = scrub_csv(raw, source_key, drop_cols, ruleset.csv_options)
        content_type = meta.get("content_type") or "text/csv"
    else:
        out = scrub_parquet(raw, drop_cols)
        content_type = meta.get("content_type") or "application/octet-stream"

    dest_key = map_dest_key(source_key, config.source_prefix, config.dest_prefix)
    put_object(
        config.dest_bucket,
        dest_key,
        out,
        content_type=content_type,
        metadata=meta.get("metadata"),
        sse=meta.get("sse"),
        kms_key_id=meta.get("kms_key_id"),
    )

    duration_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "scrubbed",
        extra={
            "source_key": source_key,
            "dest_key": dest_key,
            "format": fmt.value,
            "bytes_in": bytes_in,
            "bytes_out": len(out),
            "duration_ms": duration_ms,
            "ruleset_version": ruleset.version,
        },
    )

    return ScrubResult(
        source_bucket=source_bucket,
        source_key=source_key,
        dest_key=dest_key,
        format=fmt.value,
        bytes_in=bytes_in,
        bytes_out=len(out),
        duration_ms=duration_ms,
    )
