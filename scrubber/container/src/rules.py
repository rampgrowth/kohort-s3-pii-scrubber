"""Load and resolve scrubbing rules from S3."""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import boto3
import yaml

_s3 = boto3.client("s3")
_cached_ruleset: Ruleset | None = None


@dataclass(frozen=True)
class CsvOptions:
    delimiter: str = ","
    quotechar: str = '"'


@dataclass(frozen=True)
class Ruleset:
    version: str
    default_drop_columns: tuple[str, ...]
    overrides: tuple[tuple[str, tuple[str, ...]], ...]
    include_globs: tuple[str, ...]
    exclude_globs: tuple[str, ...]
    csv_options: CsvOptions


def get_ruleset(ruleset_uri: str) -> Ruleset:
    global _cached_ruleset
    if _cached_ruleset is not None:
        return _cached_ruleset

    parsed = urlparse(ruleset_uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.lstrip("/"):
        raise ValueError(f"Invalid RULESET_URI: {ruleset_uri}")

    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    response = _s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read()

    if key.endswith(".json"):
        data = json.loads(body)
    else:
        data = yaml.safe_load(body)

    _cached_ruleset = _parse_ruleset(data)
    return _cached_ruleset


def _parse_ruleset(data: dict[str, Any]) -> Ruleset:
    version = str(data.get("version", ""))
    if version != "1":
        raise ValueError(f"Unsupported ruleset version: {version}")

    default = data.get("default") or {}
    default_cols = tuple(default.get("drop_columns") or [])

    overrides: list[tuple[str, tuple[str, ...]]] = []
    for item in data.get("overrides") or []:
        prefix = str(item.get("prefix", ""))
        cols = tuple(item.get("drop_columns") or [])
        overrides.append((prefix, cols))

    overrides.sort(key=lambda x: len(x[0]), reverse=True)

    csv_block = data.get("csv") or {}
    csv_options = CsvOptions(
        delimiter=str(csv_block.get("delimiter", ",")),
        quotechar=str(csv_block.get("quotechar", '"')),
    )

    return Ruleset(
        version=version,
        default_drop_columns=default_cols,
        overrides=tuple(overrides),
        include_globs=tuple(data.get("include_globs") or []),
        exclude_globs=tuple(data.get("exclude_globs") or []),
        csv_options=csv_options,
    )


def should_process(ruleset: Ruleset, key: str) -> bool:
    if ruleset.exclude_globs and any(fnmatch.fnmatch(key, g) for g in ruleset.exclude_globs):
        return False
    if ruleset.include_globs:
        return any(fnmatch.fnmatch(key, g) for g in ruleset.include_globs)
    return True


def drop_columns_for_key(ruleset: Ruleset, key: str) -> tuple[str, ...]:
    columns = list(ruleset.default_drop_columns)
    for prefix, extra in ruleset.overrides:
        if prefix and key.startswith(prefix):
            for col in extra:
                if col not in columns:
                    columns.append(col)
            break
    return tuple(columns)
