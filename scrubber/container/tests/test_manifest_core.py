"""Unit tests for manifest_core helpers not already covered elsewhere."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import manifest_core  # noqa: E402


class _FakePaginator:
    def __init__(self, keys, page_size=2):
        self._keys = keys
        self._page_size = page_size

    def paginate(self, **kwargs):
        for i in range(0, len(self._keys), self._page_size):
            chunk = self._keys[i : i + self._page_size]
            yield {"Contents": [{"Key": k} for k in chunk]}


class _FakeS3:
    def __init__(self, keys):
        self._keys = keys

    def get_paginator(self, method):
        assert method == "list_objects_v2"
        return _FakePaginator(self._keys)


def test_list_existing_dest_keys_under_cap_returns_all():
    s3 = _FakeS3([f"sanitized/file-{i}.csv" for i in range(5)])
    keys = manifest_core.list_existing_dest_keys(s3, "dest", "sanitized/", max_keys=10)
    assert len(keys) == 5


def test_list_existing_dest_keys_over_cap_raises():
    s3 = _FakeS3([f"sanitized/file-{i}.csv" for i in range(10)])
    try:
        manifest_core.list_existing_dest_keys(s3, "dest", "sanitized/", max_keys=5)
    except RuntimeError as exc:
        assert "more than 5 existing objects" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when existing key count exceeds max_keys")


def test_list_existing_dest_keys_max_keys_none_disables_cap():
    s3 = _FakeS3([f"sanitized/file-{i}.csv" for i in range(10)])
    keys = manifest_core.list_existing_dest_keys(s3, "dest", "sanitized/", max_keys=None)
    assert len(keys) == 10


if __name__ == "__main__":
    test_list_existing_dest_keys_under_cap_returns_all()
    test_list_existing_dest_keys_over_cap_raises()
    test_list_existing_dest_keys_max_keys_none_disables_cap()
    print("ok")
