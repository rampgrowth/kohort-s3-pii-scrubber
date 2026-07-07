"""Unit tests for CSV scrubbing (including gzip)."""

import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csv_scrub import scrub_csv  # noqa: E402
from rules import CsvOptions  # noqa: E402


def test_scrub_csv_drops_columns():
    data = b"email,phone,age\na@x.com,111,30\n"
    out = scrub_csv(data, "sample.csv", ["email", "phone"], CsvOptions())
    text = out.decode("utf-8")
    assert "email" not in text
    assert "phone" not in text
    assert "age" in text


def test_scrub_csv_gz_drops_columns():
    plain = b"email,age\na@x.com,30\n"
    data = gzip.compress(plain)
    out = scrub_csv(data, "sample.csv.gz", ["email"], CsvOptions())
    decompressed = gzip.decompress(out).decode("utf-8")
    assert "email" not in decompressed
    assert "age" in decompressed


def test_scrub_legacy_gz_extension_drops_columns():
    """AppsFlyer Data Locker legacy keys: part-00000.gz (gzip CSV, no .csv in name)."""
    plain = b"email,age\na@x.com,30\n"
    data = gzip.compress(plain)
    out = scrub_csv(
        data,
        "kohort-datalocker/t=install/dt=2022-08-25/h=23/part-00000.gz",
        ["email"],
        CsvOptions(),
    )
    decompressed = gzip.decompress(out).decode("utf-8")
    assert "email" not in decompressed
    assert "age" in decompressed
