"""Domain contracts. No protocol SDK or persistence dependencies belong here."""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DATASET_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")


class DomainError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

    def payload(self) -> dict:
        return ErrorPayload(
            code=self.code, message=self.message, retryable=self.retryable
        ).model_dump()


def validate_dataset_id(value: str) -> None:
    if not DATASET_ID.fullmatch(value):
        raise DomainError("INVALID_INPUT", "Use a registered dataset ID, not a path or expression.")


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ErrorPayload(Model):
    status: Literal["error"] = "error"
    code: str
    message: str
    retryable: bool = False


class Column(Model):
    name: str = Field(min_length=1, max_length=128)
    dtype: Literal["text", "boolean", "int64", "decimal128", "float64", "date", "timestamp"]
    nullable: bool = True
    precision: int | None = Field(default=None, ge=1, le=38)
    scale: int | None = Field(default=None, ge=0, le=38)
    unit: Literal["s", "ms", "us", "ns"] | None = None
    timezone: Literal["UTC"] | None = None

    @model_validator(mode="after")
    def validate_parameters(self) -> Self:
        if self.name.startswith("_gdm_") or any(ord(c) < 32 for c in self.name):
            raise ValueError("Reserved or control-character column name")
        if self.dtype == "decimal128":
            if self.precision is None or self.scale is None or self.scale > self.precision:
                raise ValueError("decimal128 needs 0 <= scale <= precision <= 38")
        elif self.precision is not None or self.scale is not None:
            raise ValueError("precision/scale apply only to decimal128")
        if self.dtype == "timestamp":
            if self.unit is None:
                raise ValueError("timestamp needs an explicit unit")
        elif self.unit is not None or self.timezone is not None:
            raise ValueError("unit/timezone apply only to timestamp")
        return self


class Rule(Model):
    rule_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    explanation: str = Field(min_length=1, max_length=512)
    kind: Literal["required", "allowed_values", "bounds", "ordered"]
    column: str
    values: list[str] = Field(default_factory=list, max_length=1000)
    minimum: str | None = None
    maximum: str | None = None
    other_column: str | None = None


class MappingPair(Model):
    source: str
    target: str


class NormalizationMap(Model):
    mapping_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    explanation: str = Field(min_length=1, max_length=512)
    column: str
    pairs: list[MappingPair] = Field(min_length=1, max_length=1000)


class Contract(Model):
    schema_version: Literal[1, 2] = 1
    columns: list[Column] = Field(min_length=1, max_length=100)
    unique_key: list[str] = Field(default_factory=list, max_length=100)
    rules: list[Rule] = Field(default_factory=list, max_length=100)
    mappings: list[NormalizationMap] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_names(self) -> Self:
        names = [column.name for column in self.columns]
        if len(set(names)) != len(names):
            raise ValueError("Column names must be unique")
        if len(set(self.unique_key)) != len(self.unique_key):
            raise ValueError("Key columns must be unique")
        if not set(self.unique_key).issubset(names):
            raise ValueError("Key columns must exist")
        if self.schema_version == 1 and (self.rules or self.mappings):
            raise ValueError("Rules and mappings require contract schema_version 2")
        from guarded_data_mcp.quality import validate_contract_rules

        validate_contract_rules(self)
        return self

    def canonical_json(self) -> str:
        document = self.model_dump()
        if self.schema_version == 1:
            # Existing M1 content addresses must remain byte-for-byte compatible.
            document.pop("rules")
            document.pop("mappings")
        return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


@dataclass(frozen=True)
class Limits:
    max_source_bytes: int = 64 * 1024 * 1024
    max_rows: int = 100_000
    max_columns: int = 100
    max_cells: int = 1_000_000
    max_decoded_bytes: int = 128 * 1024 * 1024
    max_text_bytes: int = 64 * 1024
    quota_bytes: int = 2 * 1024 * 1024 * 1024
    lock_seconds: float = 5.0

    def __post_init__(self) -> None:
        ceilings = {
            "max_source_bytes": 64 * 1024 * 1024,
            "max_rows": 100_000,
            "max_columns": 100,
            "max_cells": 1_000_000,
            "max_decoded_bytes": 128 * 1024 * 1024,
            "max_text_bytes": 64 * 1024,
            "quota_bytes": 2 * 1024 * 1024 * 1024,
            "lock_seconds": 5.0,
        }
        for name, ceiling in ceilings.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not 0 < value <= ceiling:
                raise ValueError(f"{name} must be positive and at most {ceiling}")


DEFAULT_LIMITS = Limits()


class DatasetSummary(Model):
    dataset_id: str
    version: int
    row_count: int
    column_count: int
    quality_status: Literal["not_evaluated"] = "not_evaluated"


class DatasetPage(Model):
    status: Literal["ok"] = "ok"
    datasets: list[DatasetSummary]
    next_after: str | None = None


class ColumnProfile(Model):
    name: str
    dtype: str
    null_count: int


class DatasetInspection(Model):
    status: Literal["ok"] = "ok"
    dataset_id: str
    version: int
    row_count: int
    column_count: int
    contract_sha256: str
    source_sha256: str
    snapshot_sha256: str
    source_format: Literal["csv", "parquet"]
    contract: Contract
    columns: list[ColumnProfile]
    profile_complete: Literal[True] = True
    head_revision: int
    physical_contract_sha256: str
    quality_status: Literal["no_violations", "violations"]
    findings_evaluated: Literal[True] = True
    analysis_complete: Literal[True] = True
    findings: list["Finding"]


class Finding(Model):
    finding_id: str
    rule_id: str
    kind: str
    row_count: int
    sample_row_ids: list[int]
    evidence_truncated: bool


class Predicate(Model):
    column: str = Field(min_length=1, max_length=128)
    op: Literal["eq", "ne", "in", "lt", "lte", "gt", "gte", "is_null", "is_not_null"]
    values: list[str] = Field(default_factory=list, max_length=100)


class Cell(Model):
    dtype: str
    value: str | None


class Record(Model):
    row_id: int
    cells: dict[str, Cell]


class RecordPage(Model):
    status: Literal["ok"] = "ok"
    dataset_id: str
    version: int
    head_revision: int
    contract_sha256: str
    records: list[Record]
    matched_count: int
    analysis_complete: Literal[True] = True
    evidence_truncated: bool
    next_cursor: str | None = None


class DeduplicateStep(Model):
    kind: Literal["deduplicate"]


class NormalizeStep(Model):
    kind: Literal["normalize"]
    mapping_id: str = Field(min_length=1, max_length=64)
    allow_key_change: bool = False


class QuarantineStep(Model):
    kind: Literal["quarantine"]
    rule_id: str = Field(min_length=1, max_length=160)
    finding_kind: Literal[
        "required",
        "allowed_values",
        "bounds",
        "ordered",
        "missing_key",
        "exact_duplicate",
        "conflicting_key",
    ]
    row_ids: list[int] = Field(min_length=1, max_length=100_000)

    @field_validator("row_ids")
    @classmethod
    def distinct_occurrences(cls, values: list[int]) -> list[int]:
        if any(v < 1 for v in values) or len(set(values)) != len(values):
            raise ValueError("Occurrence IDs must be positive and distinct")
        return sorted(values)


RepairStep = Annotated[
    DeduplicateStep | NormalizeStep | QuarantineStep, Field(discriminator="kind")
]


class PlanRequest(Model):
    steps: list[RepairStep] = Field(min_length=1, max_length=20)


class PlanBinding(Model):
    dataset_id: str
    version: int
    head_revision: int
    contract_sha256: str
    snapshot_sha256: str
    quarantine_sha256: str


class Effect(Model):
    effect_id: int
    step_index: int
    kind: Literal["normalize", "deduplicate", "quarantine"]
    row_id: int
    column: str | None = None
    before: Cell | None = None
    after: Cell | None = None
    survivor_row_id: int | None = None
    rule_id: str | None = None
    finding_kind: str | None = None
    finding_id: str | None = None
    reason: str | None = None


class PlanDocument(Model):
    schema_version: Literal[1] = 1
    binding: PlanBinding
    contract: Contract
    request: PlanRequest
    input_row_count: int
    output_row_count: int
    quarantine_row_count: int
    active_preview_sha256: str
    quarantine_preview_sha256: str
    findings_before: list[Finding]
    predicted_findings: list[Finding]
    effects: list[Effect] = Field(max_length=100_000)
    analysis_complete: Literal[True] = True
    postconditions_passed: Literal[True] = True

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    @property
    def plan_id(self) -> str:
        return "plan_" + hashlib.sha256(self.canonical_json().encode()).hexdigest()


class StepSummary(Model):
    step_index: int
    kind: str
    mapping_id: str | None = None
    allow_key_change: bool = False
    rule_id: str | None = None
    finding_kind: str | None = None
    selected_row_count: int | None = None


class PlanPage(Model):
    status: Literal["ok"] = "ok"
    plan_id: str
    binding: PlanBinding
    state: Literal["prepared", "stale"]
    approval_status: Literal["not_supported"] = "not_supported"
    execution_status: Literal["not_enabled"] = "not_enabled"
    can_apply: Literal[False] = False
    steps: list[StepSummary]
    input_row_count: int
    output_row_count: int
    quarantine_row_count: int
    active_preview_sha256: str
    quarantine_preview_sha256: str
    findings_before: list[Finding]
    predicted_findings: list[Finding]
    analysis_complete: Literal[True] = True
    postconditions_passed: Literal[True] = True
    effect_count: int
    effects: list[Effect]
    evidence_truncated: bool
    next_after_effect: int | None = None
