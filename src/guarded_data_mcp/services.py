"""Shared import and inspection services; neither protocol handlers nor human authority."""

import base64
import hashlib
import hmac
import json
import re
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
    PlanBinding,
    PlanDocument,
    PlanPage,
    PlanRequest,
    Predicate,
    Record,
    RecordPage,
    StepSummary,
    validate_dataset_id,
)
from guarded_data_mcp.ingest import decode_source, read_source
from guarded_data_mcp.planning import simulate
from guarded_data_mcp.quality import Analysis, deadline_check, parse_value, wire_value
from guarded_data_mcp.storage import Store


class DatasetService:
    def __init__(self, workspace: Path, limits: Limits = DEFAULT_LIMITS):
        self.limits = limits
        self.store = Store(workspace, limits)
        self._cursor_key = secrets.token_bytes(32)

    @staticmethod
    def _plan_binding(dataset_id: str, record: dict, contract: Contract) -> PlanBinding:
        return PlanBinding(
            dataset_id=dataset_id,
            version=record["version"],
            head_revision=record["head_revision"],
            contract_sha256=contract.sha256,
            snapshot_sha256=record["snapshot_sha256"],
            quarantine_sha256=hashlib.sha256(record["quarantine"]).hexdigest(),
        )

    def prepare_plan(
        self, dataset_id: str, request: PlanRequest, expected_revision: int
    ) -> PlanPage:
        deadline = time.monotonic() + 30
        if (
            not isinstance(request, PlanRequest)
            or type(expected_revision) is not int
            or expected_revision < 1
        ):
            raise DomainError(
                "INVALID_INPUT", "Supply a structured plan and positive reviewed revision."
            )
        record, contract, table = self._load(dataset_id)
        if record["head_revision"] != expected_revision:
            raise DomainError("STALE_REVISION", "Investigated dataset revision has changed.")
        binding = self._plan_binding(dataset_id, record, contract)
        quarantine = decode_snapshot(record["quarantine"], binding.quarantine_sha256, contract, 0)
        document, active, quarantined = simulate(
            table, quarantine, contract, binding, request, self.limits, deadline
        )
        response = self._plan_page(document, stale=False, after_effect=0, limit=50)
        self.store.save_plan(document, active, quarantined, deadline)
        return response

    def _read_plan(self, plan_id: str) -> PlanDocument:
        if not isinstance(plan_id, str) or not re.fullmatch(r"plan_[0-9a-f]{64}", plan_id):
            raise DomainError(
                "INVALID_INPUT", "Supply a registered plan ID, not a path or expression."
            )
        stored = self.store.read_plan(plan_id)
        try:
            document = PlanDocument.model_validate_json(stored["document"])
            if document.plan_id != plan_id or document.binding.dataset_id != stored["dataset_id"]:
                raise ValueError("Plan checksum mismatch")
            if document.contract.sha256 != document.binding.contract_sha256:
                raise ValueError("Frozen contract checksum mismatch")
            if [e.effect_id for e in document.effects] != list(range(1, len(document.effects) + 1)):
                raise ValueError("Manifest sequence mismatch")
        except (ValidationError, ValueError) as exc:
            raise DomainError("STORAGE_INTEGRITY", "Stored plan failed integrity checks.") from exc
        decode_snapshot(
            stored["active_preview"],
            document.active_preview_sha256,
            document.contract,
            document.output_row_count,
        )
        decode_snapshot(
            stored["quarantine_preview"],
            document.quarantine_preview_sha256,
            document.contract,
            document.quarantine_row_count,
        )
        return document

    def review_plan(self, plan_id: str) -> dict:
        """Human CLI: complete frozen contract, request and occurrence manifest."""
        return self._read_plan(plan_id).model_dump(mode="json")

    def get_plan(self, plan_id: str, after_effect: int = 0, limit: int = 50) -> PlanPage:
        if (
            type(after_effect) is not int
            or after_effect < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise DomainError("INVALID_INPUT", "Use a nonnegative effect position and limit 1–100.")
        document = self._read_plan(plan_id)
        record, contract, _ = self._load(document.binding.dataset_id)
        stale = (
            self._plan_binding(document.binding.dataset_id, record, contract) != document.binding
        )
        return self._plan_page(document, stale, after_effect, limit)

    def _plan_page(
        self, document: PlanDocument, stale: bool, after_effect: int, limit: int
    ) -> PlanPage:
        if after_effect > len(document.effects):
            raise DomainError("INVALID_INPUT", "Effect position exceeds the immutable manifest.")
        steps = []
        for index, step in enumerate(document.request.steps, start=1):
            values = step.model_dump()
            rows = values.pop("row_ids", None)
            steps.append(
                StepSummary(
                    step_index=index,
                    **values,
                    selected_row_count=len(rows) if rows is not None else None,
                )
            )
        page = PlanPage(
            plan_id=document.plan_id,
            binding=document.binding,
            state="stale" if stale else "prepared",
            steps=steps,
            input_row_count=document.input_row_count,
            output_row_count=document.output_row_count,
            quarantine_row_count=document.quarantine_row_count,
            active_preview_sha256=document.active_preview_sha256,
            quarantine_preview_sha256=document.quarantine_preview_sha256,
            findings_before=document.findings_before,
            predicted_findings=document.predicted_findings,
            effect_count=len(document.effects),
            effects=[],
            evidence_truncated=False,
        )
        size = len(page.model_dump_json().encode()) + 1024
        effects = []
        for effect in document.effects[after_effect : after_effect + limit]:
            extra = len(effect.model_dump_json().encode())
            if size + extra > 256 * 1024:
                if not effects:
                    raise DomainError(
                        "RESOURCE_LIMIT", "An effect exceeds the bounded review payload."
                    )
                break
            effects.append(effect)
            size += extra
        more = after_effect + len(effects) < len(document.effects)
        return self._bounded(
            page.model_copy(
                update={
                    "effects": effects,
                    "evidence_truncated": more,
                    "next_after_effect": effects[-1].effect_id if more else None,
                }
            )
        )

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
