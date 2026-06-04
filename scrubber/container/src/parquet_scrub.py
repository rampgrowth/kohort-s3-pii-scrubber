"""Parquet column dropping via PyArrow."""

from __future__ import annotations

import io
from typing import Iterable

import pyarrow.parquet as pq

# Parquet metadata codec strings -> pyarrow write_table compression argument.
_CODEC_TO_WRITE: dict[str, str] = {
    "GZIP": "gzip",
    "SNAPPY": "snappy",
    "ZSTD": "zstd",
    "LZ4": "lz4",
    "LZ4_RAW": "lz4",
    "BROTLI": "brotli",
    "UNCOMPRESSED": "none",
    "NONE": "none",
}

_DEFAULT_WRITE_COMPRESSION = "snappy"


def _compression_from_parquet_file(pf: pq.ParquetFile) -> str:
    """Pick a single write compression based on source column chunk codecs."""
    counts: dict[str, int] = {}
    meta = pf.metadata
    for rg_idx in range(meta.num_row_groups):
        rg = meta.row_group(rg_idx)
        for col_idx in range(rg.num_columns):
            codec = rg.column(col_idx).compression
            if not codec:
                continue
            counts[codec] = counts.get(codec, 0) + 1

    if not counts:
        return _DEFAULT_WRITE_COMPRESSION

    # Prefer the most common codec in the file (AppsFlyer parts are uniform).
    source_codec = max(counts, key=counts.get)
    return _CODEC_TO_WRITE.get(source_codec.upper(), _DEFAULT_WRITE_COMPRESSION)


def scrub_parquet(data: bytes, drop_columns: Iterable[str]) -> bytes:
    drop_set = set(drop_columns)
    if not drop_set:
        return data

    buf = io.BytesIO(data)
    pf = pq.ParquetFile(buf)
    table = pf.read()

    existing = [name for name in table.column_names if name in drop_set]
    if not existing:
        return data

    remaining = [name for name in table.column_names if name not in drop_set]
    if not remaining:
        raise ValueError("All columns would be removed from Parquet file")

    compression = _compression_from_parquet_file(pf)
    filtered = table.select(remaining)
    out = io.BytesIO()
    pq.write_table(filtered, out, compression=compression)
    return out.getvalue()
