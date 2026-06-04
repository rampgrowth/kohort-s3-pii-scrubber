"""S3 Batch key normalization."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from s3_io import normalize_batch_object_key  # noqa: E402


def test_normalize_leaves_plain_key_unchanged():
    key = "kohort-datalocker/t=installs/dt=2025-09-28/h=0/part-00000.gz.parquet"
    assert normalize_batch_object_key(key) == key


def test_normalize_decodes_batch_url_encoding():
    encoded = "kohort-datalocker/t%3Dinstalls/dt%3D2025-09-28/h%3D0/part-00000.gz.parquet"
    assert normalize_batch_object_key(encoded) == (
        "kohort-datalocker/t=installs/dt=2025-09-28/h=0/part-00000.gz.parquet"
    )
