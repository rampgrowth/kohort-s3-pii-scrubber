"""
AWS Lambda entrypoint for S3 Batch Operations invoke.

https://docs.aws.amazon.com/AmazonS3/latest/userguide/batch-ops-invoke-lambda.html
"""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any

from config import load_config
from rules import get_ruleset
from s3_io import normalize_batch_object_key, parse_bucket_arn
from scrub import scrub_object

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    config = load_config()
    ruleset = get_ruleset(config.ruleset_uri)

    invocation_id = event.get("invocationId", "")
    results: list[dict[str, str]] = []

    for task in event.get("tasks", []):
        task_id = task["taskId"]
        source_key = normalize_batch_object_key(task["s3Key"])
        bucket_arn = task["s3BucketArn"]
        source_bucket = parse_bucket_arn(bucket_arn)

        try:
            result = scrub_object(config, ruleset, source_bucket, source_key)
            if result.skipped:
                results.append(
                    {
                        "taskId": task_id,
                        "resultCode": "Succeeded",
                        "resultString": json.dumps({"status": "skipped", "key": source_key}),
                    }
                )
            else:
                results.append(
                    {
                        "taskId": task_id,
                        "resultCode": "Succeeded",
                        "resultString": json.dumps(
                            {
                                "status": "ok",
                                "source_key": source_key,
                                "dest_key": result.dest_key,
                                "format": result.format,
                                "bytes_in": result.bytes_in,
                                "bytes_out": result.bytes_out,
                                "duration_ms": result.duration_ms,
                            }
                        ),
                    }
                )
        except Exception as exc:
            logger.error(
                "task_failed",
                extra={"task_id": task_id, "source_key": source_key, "error": str(exc)},
            )
            logger.debug(traceback.format_exc())
            results.append(
                {
                    "taskId": task_id,
                    "resultCode": "PermanentFailure",
                    "resultString": str(exc)[:1024],
                }
            )

    return {
        "invocationSchemaVersion": event.get("invocationSchemaVersion", "1.0"),
        "treatMissingKeysAs": event.get("treatMissingKeysAs", "PermanentFailure"),
        "invocationId": invocation_id,
        "results": results,
    }
