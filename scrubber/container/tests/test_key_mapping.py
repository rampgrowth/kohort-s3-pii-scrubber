"""Unit tests for S3 key mapping."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from s3_io import map_dest_key  # noqa: E402


def test_map_dest_key():
    assert (
        map_dest_key("raw/acme/file.parquet", "raw/", "sanitized/")
        == "sanitized/acme/file.parquet"
    )
    assert map_dest_key("raw/file.csv", "raw/", "") == "file.csv"
