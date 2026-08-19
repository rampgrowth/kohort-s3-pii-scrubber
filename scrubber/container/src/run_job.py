"""Shared 'run one prefix' orchestration.

Lists a source prefix, builds an incremental S3 Batch manifest, and (unless the
manifest is empty) creates an S3 Batch Operations job that invokes the scrubber
Lambda. Used by both the CLI (`scripts/kohort_sanitize.py run`) and the
scheduled orchestrator Lambda (`orchestrator.py`) so daily and manual runs share
identical behaviour.

Empty manifests are a normal outcome for a daily schedule (nothing new to
scrub). With ``allow_empty=True`` an empty listing returns a result with
``job_id=None`` and ``skipped_empty=True`` instead of raising / erroring.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from manifest_core import (
    DEFAULT_EXCLUDE_GLOBS,
    iter_manifest_rows,
    list_existing_dest_keys,
    load_ruleset_globs,
    write_manifest,
)


@dataclass(frozen=True)
class RunResult:
    prefix: str
    matching_objects: int
    job_id: str | None
    skipped_empty: bool
    manifest_uri: str | None


def slug_from_prefix(prefix: str) -> str:
    slug = prefix.strip("/").replace("/", "-")
    slug = re.sub(r"[^a-zA-Z0-9._=-]+", "-", slug)
    return slug.strip("-") or "manifest"


def resolve_prefix(source_prefix: str, prefix: str) -> str:
    """Resolve a prefix relative to source_prefix (mirror of the CLI helper).

    Accepts a prefix relative to source_prefix (e.g. "t=installs/") or a full
    key prefix that already starts with source_prefix.
    """
    src = source_prefix
    if not prefix or prefix == src or f"{prefix}/" == src:
        return src
    if prefix.startswith(src):
        return prefix
    return f"{src}{prefix.lstrip('/')}"


def _scoped_dest_list_prefix(prefix: str, source_prefix: str, dest_prefix: str) -> str:
    relative = prefix
    if source_prefix and prefix.startswith(source_prefix):
        relative = prefix[len(source_prefix):]
    return f"{dest_prefix}{relative}" if dest_prefix else relative


def _create_batch_job(
    *,
    s3_client,
    s3control_client,
    account_id: str,
    config_bucket: str,
    manifest_key: str,
    batch_reports_prefix: str,
    batch_role_arn: str,
    lambda_arn: str,
) -> str:
    etag = s3_client.head_object(Bucket=config_bucket, Key=manifest_key)["ETag"].strip('"')

    manifest = {
        "Spec": {"Format": "S3BatchOperations_CSV_20180820", "Fields": ["Bucket", "Key"]},
        "Location": {
            "ObjectArn": f"arn:aws:s3:::{config_bucket}/{manifest_key}",
            "ETag": etag,
        },
    }
    report = {
        "Bucket": f"arn:aws:s3:::{config_bucket}",
        "Prefix": batch_reports_prefix,
        "Format": "Report_CSV_20180820",
        "Enabled": True,
        "ReportScope": "AllTasks",
    }
    response = s3control_client.create_job(
        AccountId=account_id,
        ConfirmationRequired=False,
        Priority=10,
        RoleArn=batch_role_arn,
        Operation={"LambdaInvoke": {"FunctionArn": lambda_arn}},
        Manifest=manifest,
        Report=report,
        ClientRequestToken=f"scrub-{int(time.time() * 1000)}",
    )
    return response["JobId"]


def run_prefix(
    *,
    s3_client,
    s3control_client,
    account_id: str,
    raw_bucket: str,
    source_prefix: str,
    prefix: str,
    dest_bucket: str,
    dest_prefix: str,
    ruleset_uri: str,
    config_bucket: str,
    manifests_prefix: str,
    batch_reports_prefix: str,
    batch_role_arn: str,
    lambda_arn: str,
    full: bool = False,
    allow_empty: bool = True,
    dry_run: bool = False,
    log=print,
) -> RunResult:
    """List ``prefix`` under ``raw_bucket``, build a manifest, and start a Batch job.

    ``prefix`` must already be resolved (absolute key prefix under source_prefix);
    callers use :func:`resolve_prefix`.
    """
    manifest_key = f"{manifests_prefix}{slug_from_prefix(prefix)}.csv"
    manifest_uri = f"s3://{config_bucket}/{manifest_key}"

    include_globs, exclude_globs = load_ruleset_globs(ruleset_uri, s3_client)
    if not exclude_globs and not include_globs:
        exclude_globs = DEFAULT_EXCLUDE_GLOBS

    existing_dest_keys = None
    if not full:
        list_prefix = _scoped_dest_list_prefix(prefix, source_prefix, dest_prefix)
        log(f"Incremental: listing existing objects in s3://{dest_bucket}/{list_prefix}")
        existing_dest_keys = list_existing_dest_keys(s3_client, dest_bucket, list_prefix)
        log(f"  found {len(existing_dest_keys)} existing sanitized objects")

    rows = list(
        iter_manifest_rows(
            s3_client,
            raw_bucket,
            prefix,
            include_globs=include_globs,
            exclude_globs=exclude_globs,
            skip_zero_byte=True,
            max_keys=None,
            existing_dest_keys=existing_dest_keys,
            source_prefix=source_prefix,
            dest_prefix=dest_prefix,
        )
    )

    log(f"prefix={prefix!r} matching_objects={len(rows)}")

    if not rows:
        if allow_empty:
            log("Nothing to do: no new objects to scrub for this prefix.")
            return RunResult(
                prefix=prefix,
                matching_objects=0,
                job_id=None,
                skipped_empty=True,
                manifest_uri=None,
            )
        raise RuntimeError(
            f"No objects matched prefix {prefix!r}. Check the prefix, ruleset globs, "
            "and s3:ListBucket permissions."
        )

    if dry_run:
        return RunResult(
            prefix=prefix,
            matching_objects=len(rows),
            job_id=None,
            skipped_empty=False,
            manifest_uri=None,
        )

    write_manifest(rows, manifest_uri, s3_client)
    log(f"Wrote {len(rows)} rows to {manifest_uri}")

    job_id = _create_batch_job(
        s3_client=s3_client,
        s3control_client=s3control_client,
        account_id=account_id,
        config_bucket=config_bucket,
        manifest_key=manifest_key,
        batch_reports_prefix=batch_reports_prefix,
        batch_role_arn=batch_role_arn,
        lambda_arn=lambda_arn,
    )
    log(f"Batch job created: {job_id}")

    return RunResult(
        prefix=prefix,
        matching_objects=len(rows),
        job_id=job_id,
        skipped_empty=False,
        manifest_uri=manifest_uri,
    )
