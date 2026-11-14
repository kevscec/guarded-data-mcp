"""Human-only, bounded local file acquisition and explicit CSV/Parquet decoding."""

from pathlib import Path
from time import monotonic

import pyarrow as pa
import pyarrow.csv as csv
import pyarrow.parquet as pq

from guarded_data_mcp.codec import arrow_schema, collect_batches, validate_shape
from guarded_data_mcp.domain import Contract, DomainError, Limits


def read_source(path: Path, limits: Limits) -> bytes:
    try:
        with path.open("rb") as handle:
            raw = handle.read(limits.max_source_bytes + 1)
    except OSError as exc:
        raise DomainError("SOURCE_READ_FAILED", "Could not read the local source file.") from exc
    if len(raw) > limits.max_source_bytes:
        raise DomainError("RESOURCE_LIMIT", "Source file exceeds the configured byte limit.")
    return raw


def decode_source(raw: bytes, source_format: str, contract: Contract, limits: Limits) -> pa.Table:
    deadline = monotonic() + 30.0
    try:
        if source_format == "csv":
            reader = csv.open_csv(
                pa.BufferReader(raw),
                read_options=csv.ReadOptions(
                    use_threads=False, block_size=16 * 1024 * 1024, encoding="utf8"
                ),
                parse_options=csv.ParseOptions(newlines_in_values=True, ignore_empty_lines=False),
                convert_options=csv.ConvertOptions(
                    column_types=arrow_schema(contract),
                    null_values=["\\N"],
                    strings_can_be_null=True,
                    quoted_strings_can_be_null=False,
                    true_values=["true"],
                    false_values=["false"],
                    check_utf8=True,
                ),
            )
        elif source_format == "parquet":
            parquet = pq.ParquetFile(pa.BufferReader(raw))
            validate_shape(parquet.metadata.num_rows, len(parquet.schema_arrow), 0, limits)
            reader = pa.RecordBatchReader.from_batches(
                parquet.schema_arrow, parquet.iter_batches(batch_size=1024, use_threads=False)
            )
        else:
            raise DomainError("INVALID_INPUT", "Source format must be csv or parquet.")
        with reader:
            return collect_batches(reader, contract, limits, deadline)
    except (pa.ArrowException, UnicodeError, ValueError) as exc:
        # Arrow conversion errors can contain raw cell values; never return those messages.
        raise DomainError(
            "INVALID_SOURCE",
            "Source cannot be decoded with the declared types and supported CSV/Parquet policy.",
        ) from exc
