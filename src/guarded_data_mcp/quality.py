"""Closed, deterministic quality rules and lossless scalar wire values (ADR-0009)."""

import hashlib
import json
import math
import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext

import pyarrow as pa

from guarded_data_mcp.domain import Column, Contract, DomainError, Finding


def parse_value(column: Column, text: str):
    """Timestamp literals are signed epoch ticks in the column's declared unit/zone.

    Decimal literals never pass through float; float literals use hexadecimal bits.
    Requiring canonical literals avoids ambiguous approval documents and query identities.
    """
    try:
        match column.dtype:
            case "text":
                if len(text.encode("utf-8")) > 65536:
                    raise ValueError("Text literal too large")
                return text
            case "boolean":
                if text not in ("true", "false"):
                    raise ValueError("Expected true or false")
                return text == "true"
            case "int64" | "timestamp":
                if not re.fullmatch(r"0|-?[1-9][0-9]*", text) or len(text) > 20:
                    raise ValueError("Expected canonical int64")
                value = int(text)
                if not -(2**63) <= value < 2**63:
                    raise ValueError("Outside int64")
                return value
            case "decimal128":
                if len(text) > 80:
                    raise ValueError("Decimal literal too large")
                with localcontext() as context:
                    context.prec = 80
                    value = Decimal(text)
                    if not value.is_finite():
                        raise ValueError("Expected finite decimal")
                    quantum = Decimal(1).scaleb(-column.scale)
                    if value != value.quantize(quantum):
                        raise ValueError("Decimal would lose precision")
                    value = value.quantize(quantum)
                    if abs(value) >= Decimal(10) ** (column.precision - column.scale):
                        raise ValueError("Outside decimal precision")
                    if format(value, "f") != text:
                        raise ValueError("Expected fixed-scale decimal")
                    return value
            case "float64":
                value = float.fromhex(text)
                if not math.isfinite(value) or value.hex() != text:
                    raise ValueError("Expected canonical finite float.hex() literal")
                return value
            case "date":
                value = date.fromisoformat(text)
                if value.isoformat() != text:
                    raise ValueError("Expected ISO date")
                return value
    except (ValueError, OverflowError, InvalidOperation, UnicodeError) as exc:
        raise ValueError(f"Invalid {column.dtype} literal") from exc
    raise ValueError("Unsupported literal type")


def wire_value(column: Column, value) -> str | None:
    if value is None:
        return None
    if column.dtype == "boolean":
        return "true" if value else "false"
    if column.dtype == "float64":
        return value.hex()
    if column.dtype == "date":
        return value.isoformat()
    if column.dtype == "decimal128":
        return format(value, "f")
    return str(value)


def validate_contract_rules(contract: Contract) -> None:
    columns = {c.name: c for c in contract.columns}
    if len({r.rule_id for r in contract.rules}) != len(contract.rules):
        raise ValueError("Rule IDs must be unique")
    if len({m.mapping_id for m in contract.mappings}) != len(contract.mappings):
        raise ValueError("Mapping IDs must be unique")
    for rule in contract.rules:
        if rule.column not in columns:
            raise ValueError("Rule column must exist")
        column = columns[rule.column]
        if rule.kind != "allowed_values" and rule.values:
            raise ValueError("Values apply only to allowed_values")
        if rule.kind != "bounds" and (rule.minimum is not None or rule.maximum is not None):
            raise ValueError("Bounds apply only to bounds rules")
        if rule.kind != "ordered" and rule.other_column is not None:
            raise ValueError("Other column applies only to ordered rules")
        if rule.kind == "allowed_values":
            if not rule.values or len(set(rule.values)) != len(rule.values):
                raise ValueError("Allowed values must be nonempty and unique")
            for value in rule.values:
                parse_value(column, value)
        if rule.kind == "bounds":
            if column.dtype not in ("int64", "decimal128", "float64"):
                raise ValueError("Bounds require a numeric column")
            if rule.minimum is None and rule.maximum is None:
                raise ValueError("At least one bound is required")
            low = parse_value(column, rule.minimum) if rule.minimum is not None else None
            high = parse_value(column, rule.maximum) if rule.maximum is not None else None
            if low is not None and high is not None and low > high:
                raise ValueError("Minimum exceeds maximum")
        if rule.kind == "ordered":
            other = columns.get(rule.other_column)
            if column.dtype not in ("date", "timestamp") or other is None:
                raise ValueError("Ordered rules require two temporal columns")
            if (column.dtype, column.unit, column.timezone) != (
                other.dtype,
                other.unit,
                other.timezone,
            ):
                raise ValueError("Temporal columns must have identical types, units and zones")
    for mapping in contract.mappings:
        if mapping.column not in columns:
            raise ValueError("Mapping column must exist")
        sources = [pair.source for pair in mapping.pairs]
        if len(set(sources)) != len(sources):
            raise ValueError("Mapping source values must be unique")
        for pair in mapping.pairs:
            parse_value(columns[mapping.column], pair.source)
            parse_value(columns[mapping.column], pair.target)


def deadline_check(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise DomainError("RESOURCE_LIMIT", "Analysis deadline exceeded; no complete result.")


class Analysis:
    def __init__(self, table: pa.Table, contract: Contract, identity: dict, deadline: float):
        self.columns = {}
        for column in contract.columns:
            deadline_check(deadline)
            array = table[column.name]
            # Avoid Python datetime conversion, which cannot represent nanosecond precision.
            if column.dtype == "timestamp":
                array = array.cast(pa.int64())
            self.columns[column.name] = array.to_pylist()
        self.row_ids = table["_gdm_row_id"].to_pylist()
        self.positions: dict[str, list[int]] = {}
        self.findings: list[Finding] = []
        self.deadline = deadline
        self.identity = identity
        self.contract = contract
        self.evaluate()
        deadline_check(deadline)

    def add(self, rule_id: str, kind: str, positions: list[int]) -> None:
        if not positions:
            return
        digest = hashlib.sha256(
            json.dumps(
                [self.identity, rule_id, kind], sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        self.positions[digest] = positions
        self.findings.append(
            Finding(
                finding_id=digest,
                rule_id=rule_id,
                kind=kind,
                row_count=len(positions),
                sample_row_ids=[self.row_ids[p] for p in positions[:10]],
                evidence_truncated=len(positions) > 10,
            )
        )

    def select(self, predicate) -> list[int]:
        selected = []
        for p in range(len(self.row_ids)):
            if p % 1024 == 0:
                deadline_check(self.deadline)
            if predicate(p):
                selected.append(p)
        return selected

    def evaluate(self) -> None:
        for column in self.contract.columns:
            if not column.nullable:
                self.add(
                    f"_required:{column.name}",
                    "required",
                    self.select(lambda p, name=column.name: self.columns[name][p] is None),
                )
        if self.contract.unique_key:
            groups = {}
            missing = []
            columns = {c.name: c for c in self.contract.columns}
            for p in range(len(self.row_ids)):
                if p % 1024 == 0:
                    deadline_check(self.deadline)
                key = tuple(
                    wire_value(columns[n], self.columns[n][p]) for n in self.contract.unique_key
                )
                if None in key:
                    missing.append(p)
                else:
                    groups.setdefault(key, []).append(p)
            exact, conflict = [], []
            for positions in groups.values():
                deadline_check(self.deadline)
                if len(positions) < 2:
                    continue
                rows = {
                    tuple(wire_value(c, self.columns[c.name][p]) for c in self.contract.columns)
                    for p in positions
                }
                (exact if len(rows) == 1 else conflict).extend(positions)
            self.add("_key", "missing_key", missing)
            self.add("_key", "exact_duplicate", sorted(exact))
            self.add("_key", "conflicting_key", sorted(conflict))
        for rule in self.contract.rules:
            values = self.columns[rule.column]
            column = next(c for c in self.contract.columns if c.name == rule.column)
            if rule.kind == "required":
                positions = self.select(lambda p, values=values: values[p] is None)
            elif rule.kind == "allowed_values":
                allowed = set(rule.values)
                positions = self.select(
                    lambda p, values=values, column=column, allowed=allowed: (
                        values[p] is not None and wire_value(column, values[p]) not in allowed
                    )
                )
            elif rule.kind == "bounds":
                low = parse_value(column, rule.minimum) if rule.minimum is not None else None
                high = parse_value(column, rule.maximum) if rule.maximum is not None else None
                positions = self.select(
                    lambda p, values=values, low=low, high=high: (
                        values[p] is not None
                        and (
                            (low is not None and values[p] < low)
                            or (high is not None and values[p] > high)
                        )
                    )
                )
            else:
                other = self.columns[rule.other_column]
                positions = self.select(
                    lambda p, values=values, other=other: (
                        values[p] is not None and other[p] is not None and values[p] > other[p]
                    )
                )
            self.add(rule.rule_id, rule.kind, positions)
