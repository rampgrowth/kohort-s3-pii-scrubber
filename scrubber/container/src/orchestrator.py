"""Scheduled orchestrator Lambda entrypoint.

Triggered by an EventBridge schedule (see the `EnableSchedule` IaC path). Runs
the same incremental `run` path as the CLI for each configured prefix: list new
objects, write a manifest, and start an S3 Batch job that invokes the scrubber
Lambda. Days with nothing new complete successfully with no Batch job.

This shares the scrubber container image; the Lambda overrides the image command
to `orchestrator.lambda_handler` (the scrubber itself keeps `handler.lambda_handler`).

Configuration comes from environment variables set by the IaC:
  RAW_BUCKET, SOURCE_PREFIX, DEST_BUCKET, DEST_PREFIX, RULESET_URI,
  CONFIG_BUCKET, MANIFESTS_PREFIX, BATCH_REPORTS_PREFIX,
  BATCH_ROLE_ARN, SCRUBBER_FUNCTION_ARN, SCHEDULE_PREFIXES
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

from run_job import resolve_prefix, run_prefix

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} environment variable is required")
    return value


def _parse_prefixes(raw: str) -> list[str]:
    """Accept a JSON list (preferred) or a comma-separated string."""
    raw = raw.strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [p.strip() for p in raw.split(",") if p.strip()]
    if isinstance(parsed, str):
        return [parsed] if parsed.strip() else []
    if isinstance(parsed, list):
        return [str(p).strip() for p in parsed if str(p).strip()]
    raise ValueError(f"SCHEDULE_PREFIXES must be a JSON list or comma-separated string, got: {raw!r}")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    raw_bucket = _require_env("RAW_BUCKET")
    source_prefix = os.environ.get("SOURCE_PREFIX", "")
    dest_bucket = _require_env("DEST_BUCKET")
    dest_prefix = os.environ.get("DEST_PREFIX", "")
    ruleset_uri = _require_env("RULESET_URI")
    config_bucket = _require_env("CONFIG_BUCKET")
    manifests_prefix = _require_env("MANIFESTS_PREFIX")
    batch_reports_prefix = _require_env("BATCH_REPORTS_PREFIX")
    batch_role_arn = _require_env("BATCH_ROLE_ARN")
    lambda_arn = _require_env("SCRUBBER_FUNCTION_ARN")

    prefixes = _parse_prefixes(os.environ.get("SCHEDULE_PREFIXES", ""))
    if not prefixes:
        raise ValueError("SCHEDULE_PREFIXES is empty; nothing to schedule")

    full = bool(event.get("full")) if isinstance(event, dict) else False

    session = boto3.Session()
    s3 = session.client("s3")
    s3control = session.client("s3control")
    account_id = session.client("sts").get_caller_identity()["Account"]

    results: list[dict[str, Any]] = []
    for raw_prefix in prefixes:
        resolved = resolve_prefix(source_prefix, raw_prefix)
        logger.info("orchestrator_prefix_start prefix=%s", resolved)
        result = run_prefix(
            s3_client=s3,
            s3control_client=s3control,
            account_id=account_id,
            raw_bucket=raw_bucket,
            source_prefix=source_prefix,
            prefix=resolved,
            dest_bucket=dest_bucket,
            dest_prefix=dest_prefix,
            ruleset_uri=ruleset_uri,
            config_bucket=config_bucket,
            manifests_prefix=manifests_prefix,
            batch_reports_prefix=batch_reports_prefix,
            batch_role_arn=batch_role_arn,
            lambda_arn=lambda_arn,
            full=full,
            allow_empty=True,
            log=logger.info,
        )
        results.append(
            {
                "prefix": result.prefix,
                "matching_objects": result.matching_objects,
                "job_id": result.job_id,
                "skipped_empty": result.skipped_empty,
            }
        )
        logger.info(
            "orchestrator_prefix_done prefix=%s matching=%d job_id=%s",
            result.prefix,
            result.matching_objects,
            result.job_id,
        )

    jobs_created = sum(1 for r in results if r["job_id"])
    logger.info("orchestrator_done prefixes=%d jobs_created=%d", len(results), jobs_created)
    return {"jobs_created": jobs_created, "results": results}
