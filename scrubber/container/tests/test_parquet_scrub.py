"""Unit tests for Parquet scrubbing and compression preservation."""

import io
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from parquet_scrub import _compression_from_parquet_file, scrub_parquet  # noqa: E402


def _gzip_parquet_bytes() -> bytes:
    table = pa.table(
        {
            "email": ["a@x.com"],
            "age": ["30"],
            "country_code": ["US"],
        }
    )
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="gzip")
    return buf.getvalue()


def test_compression_from_metadata_detects_gzip():
    data = _gzip_parquet_bytes()
    pf = pq.ParquetFile(io.BytesIO(data))
    assert _compression_from_parquet_file(pf) == "gzip"


def test_scrub_parquet_preserves_gzip_codec():
    data = _gzip_parquet_bytes()
    out = scrub_parquet(data, ["email"])
    pf = pq.ParquetFile(io.BytesIO(out))
    assert pf.metadata.row_group(0).column(0).compression == "GZIP"
    table = pf.read()
    assert "email" not in table.column_names
    assert "age" in table.column_names


def test_scrub_parquet_avoid_snappy_rewrite_on_gzip_source():
    """Regression: previous default Snappy rewrite changed codec (installs part file)."""
    sample = Path("/tmp/parquet-compare/source.gz.parquet")
    if not sample.exists():
        return

    raw = sample.read_bytes()
    out = scrub_parquet(raw, ["appsflyer_id", "ip", "idfa"])
    codec = pq.ParquetFile(io.BytesIO(out)).metadata.row_group(0).column(0).compression
    assert codec == "GZIP"

    # Old behavior produced SNAPPY and ~49 KB for this 37 KB source object.
    snappy_buf = io.BytesIO()
    t = pq.read_table(io.BytesIO(raw))
    remaining = [n for n in t.column_names if n not in ("appsflyer_id", "ip", "idfa")]
    pq.write_table(t.select(remaining), snappy_buf, compression="snappy")
    assert pq.ParquetFile(io.BytesIO(snappy_buf.getvalue())).metadata.row_group(0).column(0).compression == "SNAPPY"
