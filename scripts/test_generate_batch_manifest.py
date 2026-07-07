"""Unit tests for generate_batch_manifest helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_batch_manifest import normalize_prefix, should_include_key


def test_normalize_prefix_strips_leading_slash():
    assert normalize_prefix("/foo/bar/") == "foo/bar/"


def test_should_include_respects_exclude():
    assert not should_include_key(
        "datalocker/t=installs/dt=2025-09-28/h=0/_SUCCESS",
        include_globs=("*",),
        exclude_globs=("**/_SUCCESS",),
    )


def test_should_include_requires_include_when_set():
    assert should_include_key(
        "datalocker/t=installs/dt=2025-09-28/h=0/part-00000.gz.parquet",
        include_globs=("*.gz.parquet",),
        exclude_globs=(),
    )
    assert not should_include_key(
        "datalocker/t=installs/dt=2025-09-28/h=0/readme.txt",
        include_globs=("*.gz.parquet",),
        exclude_globs=(),
    )


def test_prefix_covers_all_hour_partitions():
    key = "kohort-datalocker/t=installs/dt=2025-09-28/h=17/part-00000.gz.parquet"
    assert key.startswith(normalize_prefix("kohort-datalocker/t=installs/dt=2025-09-28/"))


if __name__ == "__main__":
    test_normalize_prefix_strips_leading_slash()
    test_should_include_respects_exclude()
    test_should_include_requires_include_when_set()
    test_prefix_covers_all_hour_partitions()
    print("ok")
