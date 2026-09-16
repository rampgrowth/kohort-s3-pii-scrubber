"""Shared S3 Batch manifest logic.

Pure listing/filtering/mapping helpers used by both the CLI
(`scripts/generate_batch_manifest.py`) and the scheduled orchestrator
(`orchestrator.py` -> `run_job.py`). Keeping this in the container `src/`
means it ships inside the Lambda image (Dockerfile `COPY src/`) and the CLI
imports the same copy, so listing/incremental behaviour never drifts.
"""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

DEFAULT_EXCLUDE_GLOBS = ("**/_SUCCESS", "**/_temporary/**")


def normalize_prefix(prefix: str) -> str:
    """Strip leading slashes; S3 object keys are never absolute paths."""
    return prefix.lstrip("/")


def map_dest_key(source_key: str, source_prefix: str, dest_prefix: str) -> str:
    """Compute the expected destination key for a source key."""
    relative = source_key
    if source_prefix and source_key.startswith(source_prefix):
        relative = source_key[len(source_prefix):]
    return f"{dest_prefix}{relative}" if dest_prefix else relative


#: Default ceiling for list_existing_dest_keys. A coarse schedule prefix (e.g.
#: "t=installs/") only grows over time, and this listing is held entirely in
#: memory; without a cap it can eventually exceed the orchestrator Lambda's
#: memory limit. Override via max_keys for buckets known to need more.
DEFAULT_MAX_EXISTING_DEST_KEYS = 2_000_000


def list_existing_dest_keys(
    s3_client,
    dest_bucket: str,
    dest_prefix: str,
    *,
    max_keys: int | None = DEFAULT_MAX_EXISTING_DEST_KEYS,
) -> frozenset[str]:
    """List all keys under dest_prefix in dest_bucket. Used for incremental filtering.

    Raises RuntimeError instead of continuing past max_keys, so a prefix that has
    grown too large to list in memory fails loudly (with a fix suggestion)
    rather than risking an OOM later in the run. Pass max_keys=None to disable.
    """
    keys: list[str] = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=dest_bucket, Prefix=normalize_prefix(dest_prefix)):
        for obj in page.get("Contents") or []:
            keys.append(obj["Key"])
            if max_keys is not None and len(keys) > max_keys:
                raise RuntimeError(
                    f"s3://{dest_bucket}/{dest_prefix} has more than {max_keys} existing "
                    "objects; incremental listing would risk exhausting memory. Narrow "
                    "the schedule prefix (e.g. add a date partition), or pass a higher "
                    "max_keys / run with full=True if this is expected."
                )
    return frozenset(keys)


def should_include_key(
    key: str,
    *,
    include_globs: tuple[str, ...],
    exclude_globs: tuple[str, ...],
) -> bool:
    """Match scrubber rules.should_process logic (fnmatch on full object key)."""
    if exclude_globs and any(fnmatch.fnmatch(key, g) for g in exclude_globs):
        return False
    if include_globs:
        return any(fnmatch.fnmatch(key, g) for g in include_globs)
    return True


def load_ruleset_globs(ruleset: str, s3_client) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Load include_globs and exclude_globs from a local path or s3:// URI."""
    import yaml

    if ruleset.startswith("s3://"):
        parsed = urlparse(ruleset)
        if not parsed.netloc or not parsed.path.lstrip("/"):
            raise ValueError(f"Invalid ruleset URI: {ruleset}")
        response = s3_client.get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
        body = response["Body"].read()
        key = parsed.path
    else:
        path = Path(ruleset)
        body = path.read_bytes()
        key = str(path)

    if key.endswith(".json"):
        data = json.loads(body)
    else:
        data = yaml.safe_load(body)

    include = tuple(data.get("include_globs") or ())
    exclude = tuple(data.get("exclude_globs") or ())
    return include, exclude


def iter_manifest_rows(
    s3_client,
    bucket: str,
    prefix: str,
    *,
    include_globs: tuple[str, ...],
    exclude_globs: tuple[str, ...],
    skip_zero_byte: bool,
    max_keys: int | None,
    existing_dest_keys: frozenset[str] | None = None,
    source_prefix: str = "",
    dest_prefix: str = "",
) -> Iterator[str]:
    """Yield CSV lines `bucket,key` for objects matching filters."""
    normalized = normalize_prefix(prefix)
    count = 0
    paginator = s3_client.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=normalized):
        for obj in page.get("Contents") or []:
            key = obj["Key"]
            if skip_zero_byte and obj.get("Size", 0) == 0:
                continue
            if not should_include_key(
                key, include_globs=include_globs, exclude_globs=exclude_globs
            ):
                continue
            if existing_dest_keys is not None:
                dest_key = map_dest_key(key, source_prefix, dest_prefix)
                if dest_key in existing_dest_keys:
                    continue
            yield f"{bucket},{key}"
            count += 1
            if max_keys is not None and count >= max_keys:
                return


def write_manifest(lines: list[str], output: str, s3_client) -> None:
    body = "\n".join(lines)
    if body:
        body += "\n"

    if output.startswith("s3://"):
        parsed = urlparse(output)
        if not parsed.netloc or not parsed.path.lstrip("/"):
            raise ValueError(f"Invalid output URI: {output}")
        s3_client.put_object(
            Bucket=parsed.netloc,
            Key=parsed.path.lstrip("/"),
            Body=body.encode("utf-8"),
            ContentType="text/csv",
        )
        return

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
