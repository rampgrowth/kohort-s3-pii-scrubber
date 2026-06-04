"""Unit tests for format detection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from formats import ObjectFormat, detect_format  # noqa: E402


def test_detect_parquet():
    assert detect_format("path/file.parquet") == ObjectFormat.PARQUET


def test_detect_gz_parquet():
    assert (
        detect_format(
            "kohort-datalocker/t=installs/dt=2025-09-28/h=0/part-00000-x-c000.gz.parquet"
        )
        == ObjectFormat.PARQUET
    )


def test_detect_csv_gz():
    assert detect_format("path/file.csv.gz") == ObjectFormat.CSV


def test_detect_legacy_gz_csv():
    assert (
        detect_format("kohort-datalocker/t=attributed_ad_revenue/dt=2022-08-25/h=23/part-00000.gz")
        == ObjectFormat.CSV
    )
