import hashlib
import json
import sqlite3
from contextlib import closing

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pydantic import ValidationError

from guarded_data_mcp.domain import Column, Contract, DomainError, Predicate
from guarded_data_mcp.services import DatasetService


def setup(tmp_path, *, key=True, rows=None):
    contract = Contract(
        columns=[Column(name="id", dtype="text"), Column(name="category", dtype="text")],
        unique_key=["id"] if key else [],
    )
    source = tmp_path / "input.csv"
    source.write_text(
        rows or "id,category\na,open\na,open\nb,open\nb,closed\n\\N,new\n", encoding="utf-8"
    )
    service = DatasetService(tmp_path / "workspace")
    service.import_file("fixture", source, "csv", contract, contract.sha256)
    return service, contract


def state(service):
    with closing(sqlite3.connect(service.store.path)) as db:
        return {
            table: db.execute(f"SELECT * FROM {table}").fetchall()
            for table in ("sources", "versions", "datasets", "contracts", "activations")
        }


def revised(contract, **kwargs):
    document = json.loads(contract.canonical_json())
    return Contract.model_validate({**document, "schema_version": 2, **kwargs})


def refusal(code, function, *args, **kwargs):
    with pytest.raises(DomainError) as caught:
        function(*args, **kwargs)
    assert caught.value.code == code


def test_distinguish_exact_conflicting_missing_and_legitimate_multiplicity(tmp_path):
    service, contract = setup(tmp_path)
    before = state(service)
    inspected = service.inspect("fixture")
    findings = {f.kind: f for f in inspected.findings}
    assert {kind: f.sample_row_ids for kind, f in findings.items()} == {
        "exact_duplicate": [1, 2],
        "conflicting_key": [3, 4],
        "missing_key": [5],
    }
    for kind, finding in findings.items():
        page = service.query_records("fixture", finding_id=finding.finding_id)
        assert [r.row_id for r in page.records] == findings[kind].sample_row_ids
    assert service.inspect("fixture").findings == inspected.findings
    assert state(service) == before
    no_key = revised(contract, unique_key=[])
    service.activate_contract("fixture", no_key, no_key.sha256, 1)
    assert service.inspect("fixture").quality_status == "no_violations"
    assert len(service.query_records("fixture").records) == 5


def test_categories_require_approved_rule_and_mapping_activation_does_not_repair(tmp_path):
    service, contract = setup(tmp_path, key=False)
    assert service.inspect("fixture").findings == []
    updated = revised(
        contract,
        rules=[
            {
                "rule_id": "category",
                "explanation": "Only published categories",
                "kind": "allowed_values",
                "column": "category",
                "values": ["open", "closed"],
            }
        ],
        mappings=[
            {
                "mapping_id": "category-map",
                "explanation": "Human equivalence",
                "column": "category",
                "pairs": [{"source": "new", "target": "open"}],
            }
        ],
    )
    before = state(service)
    refusal("CONTRACT_NOT_APPROVED", service.activate_contract, "fixture", updated, "fake", 1)
    assert state(service) == before
    result = service.activate_contract("fixture", updated, updated.sha256, 1)
    assert result["head_revision"] == 2 and not result["data_changed"]
    inspection = service.inspect("fixture")
    assert inspection.physical_contract_sha256 == contract.sha256
    assert inspection.contract_sha256 == updated.sha256
    assert [(f.kind, f.sample_row_ids) for f in inspection.findings] == [("allowed_values", [5])]
    after = state(service)
    assert {k: after[k] for k in ("sources", "versions", "datasets")} == {
        k: before[k] for k in ("sources", "versions", "datasets")
    }
    refusal("STALE_REVISION", service.activate_contract, "fixture", updated, updated.sha256, 1)
    assert state(service) == after


def test_cursor_binds_query_state_session_and_signature(tmp_path):
    service, contract = setup(tmp_path)
    page = service.query_records("fixture", limit=2)
    assert page.matched_count == 5 and page.evidence_truncated
    second = service.query_records("fixture", limit=2, cursor=page.next_cursor)
    third = service.query_records("fixture", limit=2, cursor=second.next_cursor)
    assert [r.row_id for r in page.records + second.records + third.records] == [1, 2, 3, 4, 5]
    assert third.next_cursor is None and not third.evidence_truncated
    for kwargs in (
        {"columns": ["id"]},
        {"limit": 3},
        {"predicates": [Predicate(column="id", op="eq", values=["a"])]},
    ):
        refusal(
            "STALE_CURSOR",
            service.query_records,
            "fixture",
            cursor=page.next_cursor,
            **{"limit": 2, **kwargs},
        )
    refusal(
        "INVALID_CURSOR",
        service.query_records,
        "fixture",
        limit=2,
        cursor=("B" if page.next_cursor.startswith("A") else "A") + page.next_cursor[1:],
    )
    refusal(
        "INVALID_CURSOR",
        DatasetService(service.store.path.parent).query_records,
        "fixture",
        limit=2,
        cursor=page.next_cursor,
    )
    service.activate_contract("fixture", contract, contract.sha256, 1)
    refusal("STALE_CURSOR", service.query_records, "fixture", limit=2, cursor=page.next_cursor)
    # Returning to the identical contract never resurrects an earlier revision/cursor.
    service.activate_contract("fixture", contract, contract.sha256, 2)
    refusal("STALE_CURSOR", service.query_records, "fixture", limit=2, cursor=page.next_cursor)


@pytest.mark.parametrize(
    ("op", "values", "expected"),
    [
        ("eq", ["a"], [1, 2]),
        ("ne", ["a"], [3, 4]),
        ("in", ["b", "a"], [1, 2, 3, 4]),
        ("lt", ["b"], [1, 2]),
        ("lte", ["b"], [1, 2, 3, 4]),
        ("gt", ["a"], [3, 4]),
        ("gte", ["b"], [3, 4]),
        ("is_null", [], [5]),
        ("is_not_null", [], [1, 2, 3, 4]),
    ],
)
def test_closed_filters_and_null_semantics(tmp_path, op, values, expected):
    service, _ = setup(tmp_path)
    result = service.query_records(
        "fixture", predicates=[Predicate(column="id", op=op, values=values)]
    )
    assert [r.row_id for r in result.records] == expected


@pytest.mark.parametrize(
    "kwargs",
    [
        {"columns": ["id; DROP TABLE datasets"]},
        {"columns": []},
        {"columns": ["id", "id"]},
        {"limit": 101},
        {"limit": True},
        {"predicates": [Predicate(column="unknown", op="eq", values=["a"])]},
        {"predicates": [Predicate(column="id", op="is_null", values=[""])]},
        {"predicates": [Predicate(column="id", op="eq")]},
        {"predicates": [Predicate(column="id", op="in")]},
        {"predicates": [Predicate(column="id", op="eq", values=["a"])] * 21},
    ],
)
def test_invalid_queries_preserve_entire_state(tmp_path, kwargs):
    service, _ = setup(tmp_path)
    before = state(service)
    refusal("INVALID_INPUT", service.query_records, "fixture", **kwargs)
    assert state(service) == before


def test_full_counts_bounded_samples_and_byte_budget(tmp_path):
    service, contract = setup(tmp_path, rows="id,category\n" + "a,open\n" * 120)
    finding = service.inspect("fixture").findings[0]
    assert finding.row_count == 120 and finding.evidence_truncated
    assert finding.sample_row_ids == list(range(1, 11))
    page = service.query_records("fixture", finding_id=finding.finding_id, limit=100)
    assert page.matched_count == 120 and len(page.records) == 100 and page.evidence_truncated
    large = "x" * 65536
    other = tmp_path / "large"
    other.mkdir()
    service, _ = setup(other, key=False, rows="id,category\n" + f"a,{large}\n" * 8)
    page = service.query_records("fixture", limit=100)
    assert 0 < len(page.records) < 8 and len(page.model_dump_json().encode()) <= 256 * 1024
    assert page.matched_count == 8 and page.evidence_truncated and page.next_cursor
    second = service.query_records("fixture", limit=100, cursor=page.next_cursor)
    assert second.records[0].row_id == page.records[-1].row_id + 1


def test_cursor_rejects_changed_data_version(tmp_path):
    service, _ = setup(tmp_path)
    page = service.query_records("fixture", limit=2)
    with closing(sqlite3.connect(service.store.path)) as db:
        row = list(db.execute("SELECT * FROM versions").fetchone())
        row[1] = 2
        db.execute("INSERT INTO versions VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        db.execute("UPDATE datasets SET current_version=2")
        db.commit()
    refusal("STALE_CURSOR", service.query_records, "fixture", limit=2, cursor=page.next_cursor)


def test_wire_preserves_int64_float_bits_and_timestamp_nanoseconds(tmp_path):
    contract = Contract(
        columns=[
            Column(name="i", dtype="int64"),
            Column(name="f", dtype="float64"),
            Column(name="t", dtype="timestamp", unit="ns", timezone="UTC"),
        ]
    )
    table = pa.table(
        {
            "i": pa.array([2**63 - 1, -(2**63)], type=pa.int64()),
            "f": [-0.0, 0.0],
            "t": pa.array([1700000000000000001, -1], type=pa.timestamp("ns", "UTC")),
        }
    )
    source = tmp_path / "data.parquet"
    pq.write_table(table, source)
    service = DatasetService(tmp_path / "workspace")
    service.import_file("typed", source, "parquet", contract, contract.sha256)
    page = service.query_records("typed")
    assert [r.cells["i"].value for r in page.records] == [str(2**63 - 1), str(-(2**63))]
    assert [r.cells["f"].value for r in page.records] == ["-0x0.0p+0", "0x0.0p+0"]
    assert [r.cells["t"].value for r in page.records] == ["1700000000000000001", "-1"]
    result = service.query_records(
        "typed", predicates=[Predicate(column="f", op="eq", values=["-0x0.0p+0"])]
    )
    assert [r.row_id for r in result.records] == [1]
    for value in ("NaN", "inf", "0.0"):
        refusal(
            "INVALID_INPUT",
            service.query_records,
            "typed",
            predicates=[Predicate(column="f", op="eq", values=[value])],
        )


def test_numeric_bounds_ordered_dates_and_required_are_independent(tmp_path):
    contract = Contract.model_validate(
        {
            "schema_version": 2,
            "columns": [
                {"name": "n", "dtype": "decimal128", "precision": 38, "scale": 2},
                {"name": "start", "dtype": "date"},
                {"name": "end", "dtype": "date"},
            ],
            "rules": [
                {
                    "rule_id": "range",
                    "explanation": "Inclusive",
                    "kind": "bounds",
                    "column": "n",
                    "minimum": "1.00",
                    "maximum": "2.00",
                },
                {
                    "rule_id": "present",
                    "explanation": "Required",
                    "kind": "required",
                    "column": "n",
                },
                {
                    "rule_id": "dates",
                    "explanation": "Start <= end",
                    "kind": "ordered",
                    "column": "start",
                    "other_column": "end",
                },
            ],
        }
    )
    source = tmp_path / "input.csv"
    source.write_text(
        "n,start,end\n1.00,2026-01-01,2026-01-01\n2.00,2026-01-02,2026-01-01\n"
        "2.01,\\N,2026-01-01\n\\N,\\N,\\N\n",
        encoding="utf-8",
    )
    service = DatasetService(tmp_path / "workspace")
    result = service.import_file("fixture", source, "csv", contract, contract.sha256)
    assert {f.rule_id: f.sample_row_ids for f in result.findings} == {
        "range": [3],
        "present": [4],
        "dates": [2],
    }


def test_v1_contract_hash_and_schema1_workspace_remain_compatible(tmp_path):
    service, contract = setup(tmp_path)
    document = json.loads(contract.canonical_json())
    assert "rules" not in document and "mappings" not in document
    assert (
        hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        == contract.sha256
    )
    with closing(sqlite3.connect(service.store.path)) as db:
        db.execute("DROP TABLE activations")
        db.execute("PRAGMA user_version=1")
        db.commit()
    before = state_without_activations(service)
    assert service.inspect("fixture").head_revision == 1
    assert state_without_activations(service) == before
    service.activate_contract("fixture", contract, contract.sha256, 1)
    assert service.inspect("fixture").head_revision == 2


def state_without_activations(service):
    with closing(sqlite3.connect(service.store.path)) as db:
        return db.execute("SELECT snapshot,quarantine FROM versions").fetchall()


@pytest.mark.parametrize(
    "rule",
    [
        {"kind": "required", "column": "missing"},
        {"kind": "allowed_values", "column": "id", "values": []},
        {"kind": "required", "column": "id", "values": ["x"]},
        {"kind": "bounds", "column": "id", "minimum": "a"},
        {"kind": "ordered", "column": "id", "other_column": "category"},
    ],
)
def test_invalid_rules_are_rejected(tmp_path, rule):
    _, contract = setup(tmp_path)
    with pytest.raises(ValidationError):
        revised(contract, rules=[{"rule_id": "test", "explanation": "Test", **rule}])


def test_incomplete_analysis_never_returns_success(tmp_path, monkeypatch):
    service, _ = setup(tmp_path)
    before = state(service)
    from guarded_data_mcp import quality

    def timeout(_):
        raise DomainError("RESOURCE_LIMIT", "Analysis incomplete")

    monkeypatch.setattr(quality, "deadline_check", timeout)
    refusal("RESOURCE_LIMIT", service.inspect, "fixture")
    refusal("RESOURCE_LIMIT", service.query_records, "fixture")
    assert state(service) == before


def test_oversized_contract_result_does_not_publish_import_or_activation(tmp_path):
    service, contract = setup(tmp_path)
    large = revised(
        contract,
        rules=[
            {
                "rule_id": "large",
                "explanation": "Reviewed values",
                "kind": "allowed_values",
                "column": "category",
                "values": [str(i) + "x" * 500 for i in range(1000)],
            }
        ],
    )
    before = state(service)
    refusal("RESOURCE_LIMIT", service.activate_contract, "fixture", large, large.sha256, 1)
    assert state(service) == before
    other = DatasetService(tmp_path / "other-workspace")
    refusal(
        "RESOURCE_LIMIT",
        other.import_file,
        "fixture",
        tmp_path / "input.csv",
        "csv",
        large,
        large.sha256,
    )
    assert not other.store.path.exists()


def test_schema_change_and_activation_write_failure_roll_back(tmp_path):
    service, contract = setup(tmp_path)
    before = state(service)
    incompatible = Contract(columns=[Column(name="id", dtype="int64")])
    refusal(
        "SCHEMA_CHANGE", service.activate_contract, "fixture", incompatible, incompatible.sha256, 1
    )
    assert state(service) == before
    updated = revised(contract, unique_key=[])
    with closing(sqlite3.connect(service.store.path)) as db:
        db.execute("""CREATE TRIGGER fail_activation BEFORE INSERT ON activations
                    BEGIN SELECT RAISE(ABORT, 'injected'); END""")
        db.commit()
    refusal("STORAGE_INTEGRITY", service.activate_contract, "fixture", updated, updated.sha256, 1)
    assert state(service) == before


def test_damaged_active_contract_is_refused(tmp_path):
    service, contract = setup(tmp_path)
    updated = revised(contract, unique_key=[])
    service.activate_contract("fixture", updated, updated.sha256, 1)
    with closing(sqlite3.connect(service.store.path)) as db:
        db.execute(
            "UPDATE contracts SET document=? WHERE sha256=?",
            (contract.canonical_json(), updated.sha256),
        )
        db.commit()
    refusal("STORAGE_INTEGRITY", service.inspect, "fixture")
    refusal("STORAGE_INTEGRITY", service.query_records, "fixture")


def test_duplicate_mapping_sources_and_lossy_decimal_rules_are_invalid():
    contract = Contract(columns=[Column(name="amount", dtype="decimal128", precision=38, scale=2)])
    for value in ("1.001", "NaN", "1", "1000000000000000000000000000000000000.00"):
        with pytest.raises(ValidationError):
            revised(
                contract,
                rules=[
                    {
                        "rule_id": "bounds",
                        "explanation": "Typed",
                        "kind": "bounds",
                        "column": "amount",
                        "minimum": value,
                    }
                ],
            )
    with pytest.raises(ValidationError):
        revised(
            contract,
            mappings=[
                {
                    "mapping_id": "map",
                    "explanation": "Explicit",
                    "column": "amount",
                    "pairs": [
                        {"source": "1.00", "target": "2.00"},
                        {"source": "1.00", "target": "3.00"},
                    ],
                }
            ],
        )
