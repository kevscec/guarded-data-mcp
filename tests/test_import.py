import hashlib
import sqlite3
import struct
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pydantic import ValidationError

from guarded_data_mcp.codec import arrow_schema
from guarded_data_mcp.domain import DEFAULT_LIMITS, Column, Contract, DomainError, Limits
from guarded_data_mcp.services import DatasetService


def contract(*columns, unique_key=None):
    return Contract(columns=[Column(**c) for c in columns], unique_key=unique_key or [])


def imported(
    tmp_path,
    raw,
    specification,
    *,
    limits=DEFAULT_LIMITS,
    source_format="csv",
    dataset_id="example",
):
    source = tmp_path / f"source.{source_format}"
    source.write_bytes(raw)
    service = DatasetService(tmp_path / "workspace", limits)
    result = service.import_file(
        dataset_id, source, source_format, specification, specification.sha256
    )
    return service, result


def stored_table(service):
    with closing(sqlite3.connect(service.store.path)) as connection, connection:
        blob = connection.execute("SELECT snapshot FROM versions").fetchone()[0]
    return pa.ipc.open_file(pa.BufferReader(blob)).read_all()


def test_exact_source_text_identity_nulls_and_duplicates(tmp_path):
    specification = contract(
        {"name": "id", "dtype": "text", "nullable": False},
        {"name": "note", "dtype": "text"},
        unique_key=["id"],
    )
    raw = b'id,note\r\n001,""\r\n001,""\r\n002,\\N\r\n003,"\\N"\r\n\\N,untouched\r\n'
    service, result = imported(tmp_path, raw, specification)
    assert stored_table(service).to_pylist() == [
        {"id": "001", "note": "", "_gdm_row_id": 1},
        {"id": "001", "note": "", "_gdm_row_id": 2},
        {"id": "002", "note": None, "_gdm_row_id": 3},
        {"id": "003", "note": "\\N", "_gdm_row_id": 4},
        {"id": None, "note": "untouched", "_gdm_row_id": 5},
    ]
    assert result.row_count == 5
    assert result.columns[0].null_count == 1  # Nullability is quality, not source coercion.
    assert result.quality_status == "violations"
    assert result.findings_evaluated
    assert {f.kind for f in result.findings} == {"required", "missing_key", "exact_duplicate"}
    with closing(sqlite3.connect(service.store.path)) as connection, connection:
        assert connection.execute("SELECT content FROM sources").fetchone()[0] == raw
    assert result.source_sha256 == hashlib.sha256(raw).hexdigest()


def test_all_supported_types_survive_parquet_and_sqlite(tmp_path):
    specification = contract(
        {"name": "id", "dtype": "text"},
        {"name": "flag", "dtype": "boolean"},
        {"name": "integer", "dtype": "int64"},
        {"name": "decimal", "dtype": "decimal128", "precision": 38, "scale": 9},
        {"name": "float", "dtype": "float64"},
        {"name": "date", "dtype": "date"},
        {"name": "naive", "dtype": "timestamp", "unit": "ns"},
        {"name": "aware", "dtype": "timestamp", "unit": "us", "timezone": "UTC"},
    )
    schema = arrow_schema(specification)
    table = pa.Table.from_arrays(
        [
            pa.array(["0001", "0001"]),
            pa.array([True, None]),
            pa.array([2**63 - 1, -(2**63)]),
            pa.array(
                [Decimal("12345678901234567890.123456789"), None], type=schema.field("decimal").type
            ),
            pa.array([-0.0, 1.23456789012345]),
            pa.array([1, None], type=pa.int32()).cast(pa.date32()),
            pa.array([1234567890123456789, None], type=pa.int64()).cast(pa.timestamp("ns")),
            pa.array([1234567890123456, None], type=pa.int64()).cast(pa.timestamp("us", "UTC")),
        ],
        schema=schema,
    )
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink, store_schema=True)
    service, _ = imported(
        tmp_path, sink.getvalue().to_pybytes(), specification, source_format="parquet"
    )
    actual = stored_table(service).drop(["_gdm_row_id"])
    assert actual.equals(table)
    assert struct.pack("!d", actual["float"][0].as_py()) == struct.pack("!d", -0.0)
    assert actual["naive"].cast(pa.int64()).to_pylist() == [1234567890123456789, None]


@pytest.mark.parametrize("raw", [b"n\nNaN\n", b"n\nInfinity\n", b"n\n-inf\n"])
def test_non_finite_floats_are_refused_without_partial_registration(tmp_path, raw):
    specification = contract({"name": "n", "dtype": "float64"})
    with pytest.raises(DomainError) as error:
        imported(tmp_path, raw, specification)
    assert error.value.code == "UNSUPPORTED_VALUE"
    assert not (tmp_path / "workspace" / "guarded-data.sqlite3").exists()


@pytest.mark.parametrize("raw", [b"n\n1.234\n", b"n\nnot-a-decimal\n"])
def test_decimal_loss_or_bad_values_are_not_coerced(tmp_path, raw):
    specification = contract({"name": "n", "dtype": "decimal128", "precision": 8, "scale": 2})
    with pytest.raises(DomainError) as error:
        imported(tmp_path, raw, specification)
    assert error.value.code == "INVALID_SOURCE"
    assert "not-a-decimal" not in error.value.message


@pytest.mark.parametrize("raw", [b"other\n1\n", b"n,extra\n1,x\n", b"n,n\n1,2\n"])
def test_unknown_missing_or_duplicate_columns_are_refused(tmp_path, raw):
    with pytest.raises(DomainError) as error:
        imported(tmp_path, raw, contract({"name": "n", "dtype": "int64"}))
    assert error.value.code == "SCHEMA_MISMATCH"


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_rows", 1),
        ("max_columns", 1),
        ("max_cells", 3),
        ("max_decoded_bytes", 1),
        ("max_text_bytes", 1),
        ("max_source_bytes", 1),
    ],
)
def test_limits_refuse_instead_of_truncating(tmp_path, field, value):
    specification = contract({"name": "id", "dtype": "text"}, {"name": "n", "dtype": "text"})
    with pytest.raises(DomainError) as error:
        imported(
            tmp_path,
            b"id,n\n01,ab\n02,cd\n",
            specification,
            limits=replace(Limits(), **{field: value}),
        )
    assert error.value.code == "RESOURCE_LIMIT"
    assert not (tmp_path / "workspace" / "guarded-data.sqlite3").exists()


def test_unapproved_or_changed_contract_has_no_effect(tmp_path):
    source = tmp_path / "source.csv"
    source.write_bytes(b"id\n001\n")
    service = DatasetService(tmp_path / "workspace")
    specification = contract({"name": "id", "dtype": "text"})
    with pytest.raises(DomainError, match="Review the contract"):
        service.import_file("example", source, "csv", specification, "0" * 64)
    assert not service.store.path.exists()


def test_existing_dataset_cannot_be_overwritten(tmp_path):
    specification = contract({"name": "id", "dtype": "text"})
    service, before = imported(tmp_path, b"id\n001\n", specification)
    source = tmp_path / "source.csv"
    source.write_bytes(b"id\n999\n")
    with pytest.raises(DomainError) as error:
        service.import_file("example", source, "csv", specification, specification.sha256)
    assert error.value.code == "DATASET_EXISTS"
    assert service.inspect("example") == before


def test_quota_failure_rolls_back_all_dataset_state(tmp_path):
    specification = contract({"name": "id", "dtype": "text"})
    with pytest.raises(DomainError) as error:
        imported(tmp_path, b"id\n001\n", specification, limits=replace(Limits(), quota_bytes=1))
    assert error.value.code == "RESOURCE_LIMIT"
    with closing(sqlite3.connect(tmp_path / "workspace" / "guarded-data.sqlite3")) as connection:
        for name in ["datasets", "versions", "sources", "contracts"]:
            assert connection.execute(f"SELECT count(*) FROM {name}").fetchone()[0] == 0


def test_snapshot_tampering_is_not_reported_as_valid(tmp_path):
    service, _ = imported(tmp_path, b"id\n001\n", contract({"name": "id", "dtype": "text"}))
    with closing(sqlite3.connect(service.store.path)) as connection, connection:
        connection.execute("UPDATE versions SET snapshot=?", (b"tampered",))
    with pytest.raises(DomainError) as error:
        service.inspect("example")
    assert error.value.code == "STORAGE_INTEGRITY"


def test_bounded_pagination_and_read_only_empty_workspace(tmp_path):
    service = DatasetService(tmp_path / "workspace")
    assert service.list_datasets().datasets == []
    assert not service.store.path.parent.exists()
    specification = contract({"name": "id", "dtype": "text"})
    source = tmp_path / "source.csv"
    source.write_bytes(b"id\n001\n")
    for name in ["bravo", "alpha", "charlie"]:
        service.import_file(name, source, "csv", specification, specification.sha256)
    first = service.list_datasets(2)
    assert [d.dataset_id for d in first.datasets] == ["alpha", "bravo"]
    assert first.next_after == "bravo"
    last = service.list_datasets(2, first.next_after)
    assert [d.dataset_id for d in last.datasets] == ["charlie"]
    assert last.next_after is None


@pytest.mark.parametrize(
    "column",
    [
        {"name": "x", "dtype": "nested"},
        {"name": "x", "dtype": "decimal128"},
        {"name": "x", "dtype": "timestamp"},
        {"name": "_gdm_row_id", "dtype": "text"},
        {"name": "x", "dtype": "text", "expression": "eval(...)"},
    ],
)
def test_contract_cannot_smuggle_unsupported_types_or_expressions(column):
    with pytest.raises(ValidationError):
        Contract.model_validate({"columns": [column]})


@pytest.mark.parametrize(
    "timezone,source",
    [
        ("UTC", b"t\n2024-01-01T12:00:00\n"),
        (None, b"t\n2024-01-01T12:00:00Z\n"),
    ],
)
def test_csv_does_not_invent_or_drop_timezone(tmp_path, timezone, source):
    specification = contract(
        {"name": "t", "dtype": "timestamp", "unit": "us", "timezone": timezone}
    )
    with pytest.raises(DomainError) as error:
        imported(tmp_path, source, specification)
    assert error.value.code == "INVALID_SOURCE"


def test_csv_cannot_silently_truncate_timestamp_precision(tmp_path):
    specification = contract({"name": "t", "dtype": "timestamp", "unit": "us"})
    with pytest.raises(DomainError) as error:
        imported(tmp_path, b"t\n2024-01-01T12:00:00.123456789\n", specification)
    assert error.value.code == "INVALID_SOURCE"


def test_csv_exact_decimal_float_and_nanosecond_timestamp(tmp_path):
    specification = contract(
        {"name": "d", "dtype": "decimal128", "precision": 30, "scale": 9},
        {"name": "f", "dtype": "float64"},
        {"name": "t", "dtype": "timestamp", "unit": "ns"},
    )
    service, _ = imported(
        tmp_path,
        b"d,f,t\n12345678901234567890.123456789,-0.0,2024-01-01T12:00:00.123456789\n",
        specification,
    )
    table = stored_table(service)
    assert table["d"][0].as_py() == Decimal("12345678901234567890.123456789")
    assert struct.pack("!d", table["f"][0].as_py()) == struct.pack("!d", -0.0)
    assert table["t"].cast(pa.int64())[0].as_py() % 1_000_000_000 == 123456789


def test_write_fault_rolls_back_source_contract_and_dataset(tmp_path):
    specification = contract({"name": "id", "dtype": "text"})
    service, before = imported(tmp_path, b"id\n001\n", specification)
    with closing(sqlite3.connect(service.store.path)) as connection, connection:
        connection.execute("""CREATE TRIGGER injected_failure BEFORE INSERT ON versions
            WHEN NEW.dataset_id='second'
            BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
    source = tmp_path / "second.csv"
    source.write_bytes(b"id\n999\n")
    with pytest.raises(DomainError) as error:
        service.import_file("second", source, "csv", specification, specification.sha256)
    assert error.value.code == "STORAGE_INTEGRITY"
    assert service.inspect("example") == before
    with closing(sqlite3.connect(service.store.path)) as connection:
        assert connection.execute("SELECT count(*) FROM datasets").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM sources").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM versions").fetchone()[0] == 1


def test_lock_wait_is_bounded_and_import_does_not_partially_publish(tmp_path):
    specification = contract({"name": "id", "dtype": "text"})
    service, _ = imported(tmp_path, b"id\n001\n", specification)
    limited = DatasetService(tmp_path / "workspace", replace(Limits(), lock_seconds=0.05))
    source = tmp_path / "other.csv"
    source.write_bytes(b"id\n002\n")
    with closing(sqlite3.connect(service.store.path)) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        with pytest.raises(DomainError) as error:
            limited.import_file("other", source, "csv", specification, specification.sha256)
        assert error.value.code == "STORAGE_BUSY"
        assert error.value.retryable
        assert limited.inspect("example").row_count == 1  # Read remains possible under WAL.
        blocker.rollback()
    assert [d.dataset_id for d in service.list_datasets().datasets] == ["example"]


def test_empty_parquet_and_nested_parquet_rejection(tmp_path):
    specification = contract({"name": "id", "dtype": "text"})
    sink = pa.BufferOutputStream()
    pq.write_table(pa.table({"id": pa.array([], type=pa.string())}), sink)
    _, result = imported(
        tmp_path, sink.getvalue().to_pybytes(), specification, source_format="parquet"
    )
    assert result.row_count == 0
    nested = pa.BufferOutputStream()
    pq.write_table(pa.table({"id": [["001"]]}), nested)
    source = tmp_path / "nested.parquet"
    source.write_bytes(nested.getvalue().to_pybytes())
    with pytest.raises(DomainError) as error:
        DatasetService(tmp_path / "other").import_file(
            "nested", source, "parquet", specification, specification.sha256
        )
    assert error.value.code == "SCHEMA_MISMATCH"


@pytest.mark.parametrize("attempt", range(5))
def test_two_human_cli_processes_can_register_without_lost_updates(tmp_path, attempt):
    specification = contract({"name": "id", "dtype": "text"})
    path = tmp_path / "contract.json"
    path.write_text(specification.canonical_json(), encoding="utf-8")
    source = tmp_path / "input.csv"
    source.write_bytes(b"id\n001\n")
    workspace = tmp_path / "workspace"

    def launch(name):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "guarded_data_mcp",
                "--workspace",
                str(workspace),
                "import",
                name,
                str(source),
                "--format",
                "csv",
                "--contract",
                str(path),
                "--approve-contract",
                specification.sha256,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(launch, ["first", "second"]))
    assert all(result.returncode == 0 for result in results), [r.stderr for r in results]
    service = DatasetService(workspace)
    assert [d.dataset_id for d in service.list_datasets().datasets] == ["first", "second"]
    assert service.inspect("first").row_count == service.inspect("second").row_count == 1


@pytest.mark.parametrize("rows,accepted", [(100_000, True), (100_001, False)])
def test_actual_row_ceiling(tmp_path, rows, accepted):
    specification = contract({"name": "id", "dtype": "text"})
    source = b"id\n" + b"001\n" * rows
    if accepted:
        service, result = imported(tmp_path, source, specification)
        assert result.row_count == 100_000
        assert stored_table(service).num_rows == 100_000
    else:
        with pytest.raises(DomainError) as error:
            imported(tmp_path, source, specification)
        assert error.value.code == "RESOURCE_LIMIT"


def test_text_limit_counts_utf8_bytes_not_characters(tmp_path):
    specification = contract({"name": "text", "dtype": "text"})
    with pytest.raises(DomainError) as error:
        imported(
            tmp_path,
            "text\néé\n".encode(),
            specification,
            limits=replace(Limits(), max_text_bytes=3),
        )
    assert error.value.code == "RESOURCE_LIMIT"


def test_reusing_damaged_source_is_refused_before_registration(tmp_path):
    specification = contract({"name": "id", "dtype": "text"})
    service, _ = imported(tmp_path, b"id\n001\n", specification)
    with closing(sqlite3.connect(service.store.path)) as connection, connection:
        connection.execute("UPDATE sources SET content=?", (b"corrupt",))
    with pytest.raises(DomainError) as error:
        service.import_file(
            "other", tmp_path / "source.csv", "csv", specification, specification.sha256
        )
    assert error.value.code == "STORAGE_INTEGRITY"
    assert [d.dataset_id for d in service.list_datasets().datasets] == ["example"]


def test_unavailable_workspace_returns_a_domain_error(tmp_path):
    path = tmp_path / "not-a-directory"
    path.write_bytes(b"do not overwrite")
    specification = contract({"name": "id", "dtype": "text"})
    source = tmp_path / "input.csv"
    source.write_bytes(b"id\n001\n")
    with pytest.raises(DomainError) as error:
        DatasetService(path).import_file(
            "example", source, "csv", specification, specification.sha256
        )
    assert error.value.code == "STORAGE_UNAVAILABLE"
    assert path.read_bytes() == b"do not overwrite"
