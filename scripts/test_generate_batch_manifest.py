"""Unit tests for generate_batch_manifest helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_batch_manifest import (
    iter_manifest_rows,
    list_existing_dest_keys,
    map_dest_key,
    normalize_prefix,
    should_include_key,
)


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


# --- map_dest_key ---

def test_map_dest_key_strips_source_prefix():
    assert map_dest_key(
        "appsflyer/t=installs/part-00000.parquet",
        "appsflyer/",
        "sanitized/appsflyer/",
    ) == "sanitized/appsflyer/t=installs/part-00000.parquet"


def test_map_dest_key_no_source_prefix():
    assert map_dest_key("part-00000.parquet", "", "out/") == "out/part-00000.parquet"


def test_map_dest_key_empty_dest_prefix():
    assert map_dest_key("appsflyer/file.parquet", "appsflyer/", "") == "file.parquet"


# --- list_existing_dest_keys ---

class _FakePaginator:
    def __init__(self, pages):
        self._pages = pages

    def paginate(self, **kwargs):
        return iter(self._pages)


class _FakeS3:
    def __init__(self, pages):
        self._paginator = _FakePaginator(pages)

    def get_paginator(self, method):
        assert method == "list_objects_v2"
        return self._paginator


def test_list_existing_dest_keys_collects_all_pages():
    s3 = _FakeS3([
        {"Contents": [{"Key": "sanitized/a.parquet"}, {"Key": "sanitized/b.parquet"}]},
        {"Contents": [{"Key": "sanitized/c.parquet"}]},
    ])
    result = list_existing_dest_keys(s3, "dest-bucket", "sanitized/")
    assert result == frozenset(["sanitized/a.parquet", "sanitized/b.parquet", "sanitized/c.parquet"])


def test_list_existing_dest_keys_empty_bucket():
    s3 = _FakeS3([{"Contents": None}])
    result = list_existing_dest_keys(s3, "dest-bucket", "sanitized/")
    assert result == frozenset()


# --- iter_manifest_rows with incremental filtering ---

def test_iter_manifest_rows_skips_existing():
    s3 = _FakeS3([
        {"Contents": [
            {"Key": "src/file1.parquet", "Size": 100},
            {"Key": "src/file2.parquet", "Size": 200},
            {"Key": "src/file3.parquet", "Size": 150},
        ]},
    ])
    existing = frozenset(["dest/file1.parquet", "dest/file3.parquet"])
    rows = list(iter_manifest_rows(
        s3, "my-bucket", "src/",
        include_globs=(), exclude_globs=(),
        skip_zero_byte=True, max_keys=None,
        existing_dest_keys=existing,
        source_prefix="src/",
        dest_prefix="dest/",
    ))
    assert rows == ["my-bucket,src/file2.parquet"]


def test_iter_manifest_rows_no_filter_when_none():
    s3 = _FakeS3([
        {"Contents": [
            {"Key": "src/file1.parquet", "Size": 100},
            {"Key": "src/file2.parquet", "Size": 200},
        ]},
    ])
    rows = list(iter_manifest_rows(
        s3, "my-bucket", "src/",
        include_globs=(), exclude_globs=(),
        skip_zero_byte=True, max_keys=None,
        existing_dest_keys=None,
        source_prefix="src/",
        dest_prefix="dest/",
    ))
    assert rows == ["my-bucket,src/file1.parquet", "my-bucket,src/file2.parquet"]


if __name__ == "__main__":
    test_normalize_prefix_strips_leading_slash()
    test_should_include_respects_exclude()
    test_should_include_requires_include_when_set()
    test_prefix_covers_all_hour_partitions()
    test_map_dest_key_strips_source_prefix()
    test_map_dest_key_no_source_prefix()
    test_map_dest_key_empty_dest_prefix()
    test_list_existing_dest_keys_collects_all_pages()
    test_list_existing_dest_keys_empty_bucket()
    test_iter_manifest_rows_skips_existing()
    test_iter_manifest_rows_no_filter_when_none()
    print("ok")
