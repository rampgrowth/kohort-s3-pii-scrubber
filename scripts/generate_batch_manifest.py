#!/usr/bin/env python3
"""
Generate an S3 Batch Operations manifest (headerless bucket,key CSV) from an S3 prefix.

Lists all objects under --prefix (including nested paths such as h=0, h=1, … under a
dt= partition), optionally filters with the same include/exclude globs as the scrubber
ruleset, and writes locally or uploads to s3://.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Shared listing/filtering logic lives in the scrubber container `src/` so the
# same copy ships inside the Lambda image and is imported here for the CLI.
_CONTAINER_SRC = Path(__file__).resolve().parents[1] / "scrubber/container/src"
if str(_CONTAINER_SRC) not in sys.path:
    sys.path.insert(0, str(_CONTAINER_SRC))

from manifest_core import (  # noqa: E402
    DEFAULT_EXCLUDE_GLOBS,
    iter_manifest_rows,
    list_existing_dest_keys,
    load_ruleset_globs,
    map_dest_key,
    normalize_prefix,
    should_include_key,
    write_manifest,
)

__all__ = [
    "DEFAULT_EXCLUDE_GLOBS",
    "iter_manifest_rows",
    "list_existing_dest_keys",
    "load_ruleset_globs",
    "map_dest_key",
    "normalize_prefix",
    "should_include_key",
    "write_manifest",
    "build_parser",
    "main",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate S3 Batch manifest CSV from an S3 prefix.",
    )
    parser.add_argument("--bucket", required=True, help="Source bucket containing raw objects.")
    parser.add_argument(
        "--prefix",
        required=True,
        help=(
            "List all objects whose keys start with this prefix "
            "(e.g. kohort-datalocker/t=installs/dt=2025-09-28/ includes every h=* hour)."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Local file path or s3://bucket/key for the manifest CSV.",
    )
    parser.add_argument(
        "--ruleset",
        help="Local path or s3:// URI; use include_globs / exclude_globs from the ruleset.",
    )
    parser.add_argument(
        "--include",
        action="append",
        dest="include_globs",
        metavar="GLOB",
        help="Include glob (fnmatch on full key). Repeatable. Ignored when --ruleset is set.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        dest="exclude_globs",
        metavar="GLOB",
        help=(
            "Exclude glob (fnmatch on full key). Repeatable. "
            "Defaults to **/_SUCCESS and **/_temporary/** when neither --ruleset nor --exclude is set."
        ),
    )
    parser.add_argument(
        "--include-zero-byte",
        action="store_true",
        help="Include zero-byte keys (often folder placeholders). Default: skip them.",
    )
    parser.add_argument(
        "--max-keys",
        type=int,
        metavar="N",
        help="Stop after N matching objects (safety limit for dry runs).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts only; do not write the manifest.",
    )
    parser.add_argument(
        "--dest-bucket",
        metavar="BUCKET",
        help="Destination bucket for incremental filtering (skip objects already sanitized).",
    )
    parser.add_argument(
        "--dest-prefix",
        metavar="PREFIX",
        default="",
        help="Destination prefix used for key mapping (default: empty).",
    )
    parser.add_argument(
        "--dest-list-prefix",
        metavar="PREFIX",
        help="Prefix to list in dest bucket (narrows the listing scope). Defaults to --dest-prefix.",
    )
    parser.add_argument(
        "--source-prefix",
        metavar="PREFIX",
        default="",
        help="Source prefix stripped from keys during mapping (default: empty).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Disable incremental filtering; include all matching objects even if already sanitized.",
    )
    parser.add_argument("--region", help="AWS region (default: session / AWS_REGION).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    import boto3

    session = boto3.Session(region_name=args.region)
    s3 = session.client("s3")

    if args.ruleset:
        include_globs, exclude_globs = load_ruleset_globs(args.ruleset, s3)
    else:
        include_globs = tuple(args.include_globs or ())
        if args.exclude_globs:
            exclude_globs = tuple(args.exclude_globs)
        else:
            exclude_globs = DEFAULT_EXCLUDE_GLOBS

    existing_dest_keys: frozenset[str] | None = None
    if args.dest_bucket and not args.full:
        list_prefix = args.dest_list_prefix or args.dest_prefix
        print(f"Incremental mode: listing existing objects in s3://{args.dest_bucket}/{list_prefix}")
        existing_dest_keys = list_existing_dest_keys(s3, args.dest_bucket, list_prefix)
        print(f"  found {len(existing_dest_keys)} existing sanitized objects")

    rows = list(
        iter_manifest_rows(
            s3,
            args.bucket,
            args.prefix,
            include_globs=include_globs,
            exclude_globs=exclude_globs,
            skip_zero_byte=not args.include_zero_byte,
            max_keys=args.max_keys,
            existing_dest_keys=existing_dest_keys,
            source_prefix=args.source_prefix,
            dest_prefix=args.dest_prefix,
        )
    )

    if args.dry_run:
        print(f"prefix={normalize_prefix(args.prefix)!r} matching_objects={len(rows)}")
        if rows[:3]:
            print("sample:")
            for line in rows[:3]:
                print(f"  {line}")
        if len(rows) > 3:
            print(f"  ... ({len(rows) - 3} more)")
        return 0

    if not rows:
        print(
            "No objects matched. Check --prefix (trailing / recommended), "
            "--ruleset globs, and IAM s3:ListBucket on the prefix.",
            file=sys.stderr,
        )
        return 1

    write_manifest(rows, args.output, s3)
    print(f"Wrote {len(rows)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
