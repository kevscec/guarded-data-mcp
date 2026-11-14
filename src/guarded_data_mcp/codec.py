"""Explicit Arrow types and immutable IPC snapshots stored inside SQLite (ADR-0011)."""

import hashlib
from time import monotonic

import pyarrow as pa
import pyarrow.compute as pc

from guarded_data_mcp.domain import Contract, DomainError, Limits

ROW_ID = "_gdm_row_id"


def arrow_schema(contract: Contract) -> pa.Schema:
    fields = []
    simple = {
        "text": pa.string(),
        "boolean": pa.bool_(),
        "int64": pa.int64(),
        "float64": pa.float64(),
        "date": pa.date32(),
    }
    for column in contract.columns:
        if column.dtype == "decimal128":
            dtype = pa.decimal128(column.precision, column.scale)
        elif column.dtype == "timestamp":
            dtype = pa.timestamp(column.unit, tz=column.timezone)
        else:
            dtype = simple[column.dtype]
        # Nullability is a quality rule, not permission to discard invalid source records.
        fields.append(pa.field(column.name, dtype, nullable=True))
    return pa.schema(fields)


def validate_shape(rows: int, columns: int, decoded: int, limits: Limits) -> None:
    if (
        rows > limits.max_rows
        or columns > limits.max_columns
        or rows * columns > limits.max_cells
        or decoded > limits.max_decoded_bytes
    ):
        raise DomainError("RESOURCE_LIMIT", "Dataset exceeds the configured input envelope.")


def validate_batch(batch: pa.RecordBatch, contract: Contract, limits: Limits) -> None:
    for column, values in zip(contract.columns, batch.columns, strict=True):
        if column.dtype == "float64" and len(values):
            if not pc.all(pc.fill_null(pc.is_finite(values), True)).as_py():
                raise DomainError(
                    "UNSUPPORTED_VALUE", "Non-finite float64 values are not supported."
                )
        if column.dtype == "text" and len(values):
            longest = pc.max(pc.binary_length(values)).as_py()
            if longest is not None and longest > limits.max_text_bytes:
                raise DomainError("RESOURCE_LIMIT", "A text value exceeds the configured limit.")


def collect_batches(reader, contract: Contract, limits: Limits, deadline: float) -> pa.Table:
    expected = arrow_schema(contract)
    actual = reader.schema
    if actual.names != expected.names or any(
        a.type != e.type for a, e in zip(actual, expected, strict=True)
    ):
        raise DomainError("SCHEMA_MISMATCH", "Source columns/order/types must match the contract.")
    validate_shape(0, len(actual), 0, limits)
    batches = []
    rows = decoded = 0
    for batch in reader:
        if monotonic() > deadline:
            raise DomainError("DEADLINE_EXCEEDED", "Import did not finish within its deadline.")
        rows += batch.num_rows
        decoded += batch.nbytes
        validate_shape(rows, batch.num_columns, decoded, limits)
        validate_batch(batch, contract, limits)
        # Strip source metadata and field nullability; retain logical type and all values.
        batches.append(pa.RecordBatch.from_arrays(batch.columns, schema=expected))
    if monotonic() > deadline:
        raise DomainError("DEADLINE_EXCEEDED", "Import did not finish within its deadline.")
    return pa.Table.from_batches(batches, schema=expected)


def encode_snapshot(table: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    with pa.ipc.new_file(sink, table.schema) as writer:
        writer.write_table(table)
    return sink.getvalue().to_pybytes()


def snapshot(table: pa.Table) -> bytes:
    return encode_snapshot(
        table.append_column(ROW_ID, pa.array(range(1, table.num_rows + 1), type=pa.int64()))
    )


def decode_snapshot(blob: bytes, expected_hash: str, contract: Contract, rows: int) -> pa.Table:
    if hashlib.sha256(blob).hexdigest() != expected_hash:
        raise DomainError("STORAGE_INTEGRITY", "Stored snapshot checksum does not match.")
    try:
        table = pa.ipc.open_file(pa.BufferReader(blob)).read_all()
        expected = arrow_schema(contract).append(pa.field(ROW_ID, pa.int64()))
        if not table.schema.equals(expected) or table.num_rows != rows:
            raise ValueError("Snapshot shape mismatch")
        ids = table[ROW_ID].to_pylist()
        if any(value is None or value < 1 for value in ids) or len(set(ids)) != rows:
            raise ValueError("Occurrence IDs must be positive and unique")
        return table
    except (pa.ArrowException, ValueError, KeyError) as exc:
        raise DomainError("STORAGE_INTEGRITY", "Stored snapshot is invalid.") from exc
