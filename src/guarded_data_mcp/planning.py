"""Pure ordered repair simulation. No storage, approval or publication capability."""

import hashlib
import json

import pyarrow as pa
import pyarrow.compute as pc

from guarded_data_mcp.codec import ROW_ID, encode_snapshot, validate_batch, validate_shape
from guarded_data_mcp.domain import (
    Cell,
    Contract,
    DomainError,
    Effect,
    Limits,
    PlanBinding,
    PlanDocument,
    PlanRequest,
)
from guarded_data_mcp.quality import Analysis, deadline_check, parse_value, wire_value

MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_EFFECTS = 100_000


def violations(analysis: Analysis) -> dict[tuple[str, str], set[int]]:
    return {
        (f.rule_id, f.kind): {analysis.row_ids[p] for p in analysis.positions[f.finding_id]}
        for f in analysis.findings
    }


def simulate(
    table: pa.Table,
    quarantine: pa.Table,
    contract: Contract,
    binding: PlanBinding,
    request: PlanRequest,
    limits: Limits,
    deadline: float,
) -> tuple[PlanDocument, bytes, bytes]:
    """See ADR-0013: intermediate violations may be repaired by later ordered steps."""
    original_ids = set(table[ROW_ID].to_pylist())
    if quarantine.num_rows:
        # M3 has no publication capability or prior quarantine-reason history yet.
        raise DomainError("STORAGE_INTEGRITY", "M3 expects the initial empty quarantine.")
    initial = Analysis(table, contract, binding.model_dump(exclude={"quarantine_sha256"}), deadline)
    request_sha256 = hashlib.sha256(
        json.dumps(request.model_dump(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    original_violations = violations(initial)
    effects = []
    manifest_bytes = 0

    def emit(**values) -> None:
        nonlocal manifest_bytes
        deadline_check(deadline)
        effect = Effect(effect_id=len(effects) + 1, **values)
        manifest_bytes += len(effect.model_dump_json().encode())
        if len(effects) >= MAX_EFFECTS or manifest_bytes > MAX_MANIFEST_BYTES:
            raise DomainError(
                "RESOURCE_LIMIT", "Plan effect manifest exceeds its bounded envelope."
            )
        effects.append(effect)

    for index, step in enumerate(request.steps, start=1):
        deadline_check(deadline)
        stage = Analysis(
            table,
            contract,
            {**binding.model_dump(), "simulation_step": index, "request_sha256": request_sha256},
            deadline,
        )
        remove_ids = set()
        if step.kind == "normalize":
            mapping = next((m for m in contract.mappings if m.mapping_id == step.mapping_id), None)
            if mapping is None:
                raise DomainError(
                    "UNKNOWN_MAPPING", "Mapping is not in the active approved contract."
                )
            if mapping.column in contract.unique_key and not step.allow_key_change:
                raise DomainError(
                    "KEY_CHANGE_NOT_EXPLICIT", "Key normalization requires allow_key_change."
                )
            column = next(c for c in contract.columns if c.name == mapping.column)
            pairs = {p.source: p.target for p in mapping.pairs}
            values = list(stage.columns[column.name])
            expected_wire = [wire_value(column, value) for value in values]
            for position, value in enumerate(values):
                if position % 1024 == 0:
                    deadline_check(deadline)
                before = wire_value(column, value)
                target = pairs.get(before)
                if target is None or target == before:
                    continue
                values[position] = parse_value(column, target)
                expected_wire[position] = target
                emit(
                    step_index=index,
                    kind="normalize",
                    row_id=stage.row_ids[position],
                    column=column.name,
                    before=Cell(dtype=column.dtype, value=before),
                    after=Cell(dtype=column.dtype, value=target),
                )
            dtype = table.schema.field(column.name).type
            if column.dtype == "text":
                # Check expanded text before Arrow allocates its replacement buffer.
                expanded = sum(len(value.encode()) for value in values if value is not None)
                expanded += 4 * (len(values) + 1) + (len(values) + 7) // 8
                validate_shape(
                    table.num_rows + quarantine.num_rows,
                    len(contract.columns),
                    table.nbytes - table[column.name].nbytes + expanded + quarantine.nbytes,
                    limits,
                )
            try:
                # Timestamp wire values are ticks; never round-trip through datetime.
                array = (
                    pa.array(values, type=pa.int64()).cast(dtype)
                    if column.dtype == "timestamp"
                    else pa.array(values, type=dtype)
                )
            except (pa.ArrowException, ValueError, OverflowError) as exc:
                raise DomainError(
                    "UNSUPPORTED_VALUE", "Mapping cannot preserve the declared type."
                ) from exc
            physical_values = (
                array.cast(pa.int64()) if column.dtype == "timestamp" else array
            ).to_pylist()
            if [wire_value(column, value) for value in physical_values] != expected_wire:
                raise DomainError(
                    "UNSUPPORTED_VALUE", "Mapping would change a scalar representation."
                )
            table = table.set_column(table.schema.get_field_index(column.name), column.name, array)
        elif step.kind == "deduplicate":
            if not contract.unique_key:
                raise DomainError(
                    "UNIQUE_KEY_REQUIRED", "Deduplication requires an approved unique key."
                )
            exact = next((f for f in stage.findings if f.kind == "exact_duplicate"), None)
            groups = {}
            columns = {c.name: c for c in contract.columns}
            for position in stage.positions[exact.finding_id] if exact else []:
                deadline_check(deadline)
                key = tuple(
                    wire_value(columns[n], stage.columns[n][position]) for n in contract.unique_key
                )
                groups.setdefault(key, []).append(stage.row_ids[position])
            for members in groups.values():
                survivor = min(members)
                for row_id in sorted(members):
                    if row_id != survivor:
                        remove_ids.add(row_id)
                        emit(
                            step_index=index,
                            kind="deduplicate",
                            row_id=row_id,
                            survivor_row_id=survivor,
                        )
        else:
            finding = next(
                (
                    f
                    for f in stage.findings
                    if f.rule_id == step.rule_id and f.kind == step.finding_kind
                ),
                None,
            )
            if finding is None:
                raise DomainError(
                    "UNKNOWN_FINDING", "Rule/finding is absent at this simulation step."
                )
            eligible = {stage.row_ids[p] for p in stage.positions[finding.finding_id]}
            remove_ids = set(step.row_ids)
            if not remove_ids.issubset(eligible):
                raise DomainError(
                    "INVALID_QUARANTINE_SCOPE",
                    "Every explicit row must violate the selected rule at this step.",
                )
            rule = next((r for r in contract.rules if r.rule_id == step.rule_id), None)
            reason = (
                rule.explanation
                if rule
                else f"Approved {step.finding_kind} requirement: {step.rule_id}"
            )
            for row_id in step.row_ids:
                emit(
                    step_index=index,
                    kind="quarantine",
                    row_id=row_id,
                    rule_id=step.rule_id,
                    finding_kind=step.finding_kind,
                    finding_id=finding.finding_id,
                    reason=reason,
                )
            selected = table.filter(
                pc.is_in(table[ROW_ID], value_set=pa.array(sorted(remove_ids), type=pa.int64()))
            )
            quarantine = pa.concat_tables([quarantine, selected])
        if remove_ids:
            table = table.filter(
                pc.invert(
                    pc.is_in(table[ROW_ID], value_set=pa.array(sorted(remove_ids), type=pa.int64()))
                )
            )
        for batch in table.drop([ROW_ID]).to_batches(max_chunksize=1024):
            deadline_check(deadline)
            validate_batch(batch, contract, limits)
        validate_shape(
            table.num_rows + quarantine.num_rows,
            len(contract.columns),
            table.nbytes + quarantine.nbytes,
            limits,
        )

    if not effects:
        raise DomainError("NO_EFFECT", "The complete plan changes no occurrences.")
    active_blob = encode_snapshot(table)
    quarantine = quarantine.sort_by([(ROW_ID, "ascending")])
    quarantine_blob = encode_snapshot(quarantine)
    final = Analysis(
        table,
        contract,
        {
            **binding.model_dump(),
            "simulation_final": True,
            "snapshot_sha256": hashlib.sha256(active_blob).hexdigest(),
        },
        deadline,
    )
    for requirement, row_ids in violations(final).items():
        if not row_ids.issubset(original_violations.get(requirement, set())):
            raise DomainError(
                "POSTCONDITION_FAILED",
                "Plan introduces new final rule violations; repair them in the same ordered plan.",
            )
    active_ids = set(table[ROW_ID].to_pylist())
    quarantined_ids = set(quarantine[ROW_ID].to_pylist())
    removed = {e.row_id for e in effects if e.kind == "deduplicate"}
    if (
        active_ids & quarantined_ids
        or active_ids & removed
        or quarantined_ids & removed
        or active_ids | quarantined_ids | removed != original_ids
    ):
        raise DomainError("POSTCONDITION_FAILED", "Occurrence conservation failed.")
    document = PlanDocument(
        binding=binding,
        contract=contract,
        request=request,
        input_row_count=len(original_ids),
        output_row_count=table.num_rows,
        quarantine_row_count=quarantine.num_rows,
        active_preview_sha256=hashlib.sha256(active_blob).hexdigest(),
        quarantine_preview_sha256=hashlib.sha256(quarantine_blob).hexdigest(),
        findings_before=initial.findings,
        predicted_findings=final.findings,
        effects=effects,
    )
    if len(document.canonical_json().encode()) > MAX_MANIFEST_BYTES:
        raise DomainError("RESOURCE_LIMIT", "Plan document exceeds 16 MiB.")
    deadline_check(deadline)
    return document, active_blob, quarantine_blob
