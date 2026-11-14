"""Shared import and inspection services; neither protocol handlers nor human authority."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

import pyarrow as pa
from pydantic import ValidationError

from guarded_data_mcp.codec import ROW_ID, arrow_schema, decode_snapshot, encode_snapshot, snapshot
from guarded_data_mcp.domain import (
    DEFAULT_LIMITS,
    Cell,
    ColumnProfile,
    Contract,
    DatasetInspection,
    DatasetPage,
    DatasetSummary,
    DomainError,
    Limits,
    Predicate,
    Record,
    RecordPage,
    validate_dataset_id,
)
from guarded_data_mcp.ingest import decode_source, read_source
from guarded_data_mcp.quality import Analysis, deadline_check, parse_value, wire_value
from guarded_data_mcp.storage import Store


class DatasetService:
    def __init__(self, workspace: Path, limits: Limits = DEFAULT_LIMITS):
        self.limits = limits
        self.store = Store(workspace, limits)
        self._cursor_key = secrets.token_bytes(32)

    def import_file(
        self,
        dataset_id: str,
        path: Path,
        source_format: str,
        contract: Contract,
        approved_contract_sha256: str,
    ) -> DatasetInspection:
        validate_dataset_id(dataset_id)
        if approved_contract_sha256 != contract.sha256:
            raise DomainError(
                "CONTRACT_NOT_APPROVED", "Review the contract and supply its exact SHA-256."
            )
        raw = read_source(path, self.limits)
        table = decode_source(raw, source_format, contract, self.limits)
        blob = snapshot(table)
        empty = pa.Table.from_batches(
            [], schema=arrow_schema(contract).append(pa.field(ROW_ID, pa.int64()))
        )
        # Complete analysis and result-size checks before publishing the initial version.
        record = {
            "version": 1,
            "head_revision": 1,
            "contract_sha256": contract.sha256,
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "snapshot_sha256": hashlib.sha256(blob).hexdigest(),
            "source_format": source_format,
        }
        response = self._inspection(
            dataset_id,
            record,
            contract,
            decode_snapshot(blob, record["snapshot_sha256"], contract, table.num_rows),
            time.monotonic() + 30,
        )
        self.store.register(
            dataset_id, raw, contract, source_format, blob, encode_snapshot(empty), table.num_rows
        )
        return response

    def list_datasets(self, limit: int = 50, after: str | None = None) -> DatasetPage:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise DomainError("INVALID_INPUT", "Page limit must be an integer from 1 to 100.")
        if after is not None:
            validate_dataset_id(after)
        rows = self.store.list(limit + 1, after)
        more = len(rows) > limit
        return DatasetPage(
            datasets=[DatasetSummary(**row) for row in rows[:limit]],
            next_after=rows[limit - 1]["dataset_id"] if more else None,
        )

    def _load(self, dataset_id: str, version: int | None = None):
        validate_dataset_id(dataset_id)
        if version is not None and (type(version) is not int or version < 1):
            raise DomainError("INVALID_INPUT", "Version must be a positive integer.")
        record, contract = self.store.get(dataset_id, version)
        table = decode_snapshot(
            record["snapshot"], record["snapshot_sha256"], contract, record["row_count"]
        )
        try:
            active = Contract.model_validate_json(record["active_document"])
        except ValidationError as exc:
            raise DomainError("STORAGE_INTEGRITY", "Invalid active contract.") from exc
        if active.sha256 != record["active_contract_sha256"] or arrow_schema(
            active
        ) != arrow_schema(contract):
            raise DomainError("STORAGE_INTEGRITY", "Active contract checksum/schema mismatch.")
        return record, active, table

    @staticmethod
    def _identity(dataset_id: str, record: dict, contract: Contract) -> dict:
        return {
            "dataset_id": dataset_id,
            "version": record["version"],
            "head_revision": record["head_revision"],
            "contract_sha256": contract.sha256,
            "snapshot_sha256": record["snapshot_sha256"],
        }

    @staticmethod
    def _bounded(model):
        if len(model.model_dump_json().encode()) > 256 * 1024:
            raise DomainError("RESOURCE_LIMIT", "Result exceeds 256 KiB; narrow the projection.")
        return model

    def inspect(self, dataset_id: str, version: int | None = None) -> DatasetInspection:
        deadline = time.monotonic() + 30
        record, contract, table = self._load(dataset_id, version)
        return self._inspection(dataset_id, record, contract, table, deadline)

    def _inspection(
        self, dataset_id: str, record: dict, contract: Contract, table: pa.Table, deadline: float
    ) -> DatasetInspection:
        analysis = Analysis(table, contract, self._identity(dataset_id, record, contract), deadline)
        response = DatasetInspection(
            dataset_id=dataset_id,
            version=record["version"],
            row_count=table.num_rows,
            column_count=len(contract.columns),
            contract_sha256=contract.sha256,
            source_sha256=record["source_sha256"],
            snapshot_sha256=record["snapshot_sha256"],
            source_format=record["source_format"],
            contract=contract,
            head_revision=record["head_revision"],
            physical_contract_sha256=record["contract_sha256"],
            quality_status="violations" if analysis.findings else "no_violations",
            findings=analysis.findings,
            columns=[
                ColumnProfile(
                    name=c.name, dtype=str(table[c.name].type), null_count=table[c.name].null_count
                )
                for c in contract.columns
            ],
        )
        deadline_check(deadline)
        return self._bounded(response)

    def activate_contract(
        self, dataset_id: str, contract: Contract, approved_sha256: str, expected_revision: int
    ) -> dict:
        validate_dataset_id(dataset_id)
        if approved_sha256 != contract.sha256:
            raise DomainError(
                "CONTRACT_NOT_APPROVED", "Review and supply the exact contract digest."
            )
        if type(expected_revision) is not int or expected_revision < 1:
            raise DomainError("INVALID_INPUT", "Expected revision must be a positive integer.")
        # Integrity and compatibility checks precede the transactional state recheck.
        record, old, table = self._load(dataset_id)
        if arrow_schema(contract) != arrow_schema(old):
            raise DomainError("SCHEMA_CHANGE", "Activation cannot change the physical schema.")
        reviewed = {**record, "head_revision": expected_revision + 1}
        self._inspection(dataset_id, reviewed, contract, table, time.monotonic() + 30)
        revision = self.store.activate(dataset_id, contract, expected_revision)
        return {
            "status": "ok",
            "dataset_id": dataset_id,
            "head_revision": revision,
            "contract_sha256": contract.sha256,
            "data_changed": False,
        }

    def _encode_cursor(self, context: dict, last_row_id: int) -> str:
        payload = json.dumps(
            {"context": context, "last_row_id": last_row_id}, sort_keys=True, separators=(",", ":")
        ).encode()
        signature = hmac.digest(self._cursor_key, payload, "sha256")
        return base64.urlsafe_b64encode(signature + payload).decode()

    def _decode_cursor(self, cursor: str, context: dict) -> int:
        try:
            if not isinstance(cursor, str) or len(cursor) > 2048:
                raise ValueError
            raw = base64.b64decode(cursor, altchars=b"-_", validate=True)
            signature, payload = raw[:32], raw[32:]
            if not hmac.compare_digest(signature, hmac.digest(self._cursor_key, payload, "sha256")):
                raise ValueError
            decoded = json.loads(payload)
            if decoded["context"] != context:
                raise DomainError("STALE_CURSOR", "Cursor state or query has changed.")
            position = decoded["last_row_id"]
            if type(position) is not int or position < 1:
                raise ValueError
            return position
        except (ValueError, KeyError, TypeError) as exc:
            raise DomainError(
                "INVALID_CURSOR", "Cursor is invalid or from another server session."
            ) from exc

    def query_records(
        self,
        dataset_id: str,
        version: int | None = None,
        columns: list[str] | None = None,
        predicates: list[Predicate] | None = None,
        finding_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> RecordPage:
        deadline = time.monotonic() + 30
        if type(limit) is not int or not 1 <= limit <= 100:
            raise DomainError("INVALID_INPUT", "Page limit must be an integer from 1 to 100.")
        predicates = [] if predicates is None else predicates
        if len(predicates) > 20 or any(not isinstance(p, Predicate) for p in predicates):
            raise DomainError("INVALID_INPUT", "Use at most 20 structured predicates.")
        record, contract, table = self._load(dataset_id, version)
        schema = {c.name: c for c in contract.columns}
        columns = list(schema) if columns is None else columns
        if (
            not columns
            or len(columns) > 100
            or len(set(columns)) != len(columns)
            or any(c not in schema for c in columns)
        ):
            raise DomainError("INVALID_INPUT", "Projection must name distinct registered columns.")
        identity = self._identity(dataset_id, record, contract)
        query = {
            "columns": columns,
            "predicates": [p.model_dump() for p in predicates],
            "finding_id": finding_id,
            "limit": limit,
        }
        context = {
            **identity,
            "query_sha256": hashlib.sha256(
                json.dumps(query, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }
        after = self._decode_cursor(cursor, context) if cursor is not None else 0
        analysis = Analysis(table, contract, identity, deadline)
        selected = None
        if finding_id is not None:
            if finding_id not in analysis.positions:
                raise DomainError(
                    "UNKNOWN_FINDING", "Finding is not present in this reviewed state."
                )
            selected = set(analysis.positions[finding_id])
        compiled = []
        for predicate in predicates:
            if predicate.column not in schema:
                raise DomainError("INVALID_INPUT", "Filter column is not registered.")
            expected = (
                0
                if predicate.op in ("is_null", "is_not_null")
                else (len(predicate.values) if predicate.op == "in" else 1)
            )
            if len(predicate.values) != expected or (predicate.op == "in" and not expected):
                raise DomainError("INVALID_INPUT", "Incorrect number of filter literals.")
            try:
                values = [parse_value(schema[predicate.column], v) for v in predicate.values]
            except ValueError as exc:
                raise DomainError(
                    "INVALID_INPUT", "Filter literal does not match column type."
                ) from exc
            compiled.append((predicate, values))

        def matches(position: int) -> bool:
            if selected is not None and position not in selected:
                return False
            for predicate, values in compiled:
                value = analysis.columns[predicate.column][position]
                op = predicate.op
                if op == "is_null":
                    ok = value is None
                elif op == "is_not_null":
                    ok = value is not None
                elif value is None:
                    ok = False
                elif op in ("eq", "ne", "in"):
                    # Equality is typed/representation-preserving, including signed zero.
                    column = schema[predicate.column]
                    equal = wire_value(column, value) in predicate.values
                    ok = not equal if op == "ne" else equal
                else:
                    bound = values[0]
                    ok = {
                        "lt": value < bound,
                        "lte": value <= bound,
                        "gt": value > bound,
                        "gte": value >= bound,
                    }[op]
                if not ok:
                    return False
            return True

        positions = analysis.select(matches)
        remaining = [p for p in positions if analysis.row_ids[p] > after]
        rows = []
        # Leave space for metadata/cursor and measure the final response as well.
        size = 4096
        for position in remaining[:limit]:
            row = Record(
                row_id=analysis.row_ids[position],
                cells={
                    name: Cell(
                        dtype=schema[name].dtype,
                        value=wire_value(schema[name], analysis.columns[name][position]),
                    )
                    for name in columns
                },
            )
            row_size = len(row.model_dump_json().encode())
            if size + row_size > 256 * 1024:
                if not rows:
                    raise DomainError(
                        "RESOURCE_LIMIT", "Single record exceeds result budget; narrow columns."
                    )
                break
            rows.append(row)
            size += row_size
        more = len(remaining) > len(rows)
        response = RecordPage(
            dataset_id=dataset_id,
            version=record["version"],
            head_revision=record["head_revision"],
            contract_sha256=contract.sha256,
            records=rows,
            matched_count=len(positions),
            evidence_truncated=more,
            next_cursor=self._encode_cursor(context, rows[-1].row_id) if more else None,
        )
        deadline_check(deadline)
        return self._bounded(response)
