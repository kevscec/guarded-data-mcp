"""Domain contracts. No protocol SDK or persistence dependencies belong here."""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class Contract(Model):
    schema_version: Literal[1] = 1
    columns: list[Column] = Field(min_length=1, max_length=100)
    unique_key: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_names(self) -> Self:
        names = [column.name for column in self.columns]
        if len(set(names)) != len(names):
            raise ValueError("Column names must be unique")
        if len(set(self.unique_key)) != len(self.unique_key):
            raise ValueError("Key columns must be unique")
        if not set(self.unique_key).issubset(names):
            raise ValueError("Key columns must exist")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

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
    quality_status: Literal["not_evaluated"] = "not_evaluated"
    findings_evaluated: Literal[False] = False
