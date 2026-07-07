"""Stream CSV scrubbing with optional gzip."""

from __future__ import annotations

import csv
import gzip
import io
from typing import Iterable

from rules import CsvOptions


def scrub_csv(
    data: bytes,
    key: str,
    drop_columns: Iterable[str],
    options: CsvOptions,
) -> bytes:
    drop_set = set(drop_columns)
    if not drop_set:
        return data

    input_stream = _open_input(data, key)
    text_in = io.TextIOWrapper(input_stream, encoding="utf-8", newline="")

    reader = csv.DictReader(text_in, delimiter=options.delimiter, quotechar=options.quotechar)
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")

    keep_fields = [f for f in reader.fieldnames if f not in drop_set]
    if len(keep_fields) == len(reader.fieldnames):
        return data

    out_buffer = io.BytesIO()
    out_stream: io.IOBase
    if key.lower().endswith(".gz"):
        out_stream = gzip.GzipFile(fileobj=out_buffer, mode="wb")
    else:
        out_stream = out_buffer

    text_out = io.TextIOWrapper(out_stream, encoding="utf-8", newline="")
    writer = csv.DictWriter(
        text_out,
        fieldnames=keep_fields,
        delimiter=options.delimiter,
        quotechar=options.quotechar,
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in reader:
        writer.writerow({k: row.get(k, "") for k in keep_fields})

    # Ensure wrappers are torn down in the right order.
    # Detach prevents TextIOWrapper from closing the underlying stream.
    text_out.flush()
    text_out.detach()
    if isinstance(out_stream, gzip.GzipFile):
        out_stream.close()

    return out_buffer.getvalue()


def _open_input(data: bytes, key: str) -> io.BufferedReader:
    raw = io.BytesIO(data)
    if key.lower().endswith(".gz"):
        return gzip.GzipFile(fileobj=raw, mode="rb")  # type: ignore[return-value]
    return io.BufferedReader(raw)
