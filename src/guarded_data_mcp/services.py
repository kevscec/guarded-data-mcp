"""Shared import and inspection services; neither protocol handlers nor human authority."""

from pathlib import Path

import pyarrow as pa

from guarded_data_mcp.codec import ROW_ID, arrow_schema, decode_snapshot, encode_snapshot, snapshot
from guarded_data_mcp.domain import (
    DEFAULT_LIMITS,
    ColumnProfile,
    Contract,
    DatasetInspection,
    DatasetPage,
    DatasetSummary,
    DomainError,
    Limits,
    validate_dataset_id,
)
from guarded_data_mcp.ingest import decode_source, read_source
from guarded_data_mcp.storage import Store


class DatasetService:
    def __init__(self, workspace: Path, limits: Limits = DEFAULT_LIMITS):
        self.limits = limits
        self.store = Store(workspace, limits)

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
        self.store.register(
            dataset_id, raw, contract, source_format, blob, encode_snapshot(empty), table.num_rows
        )
        return self.inspect(dataset_id)

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

    def inspect(self, dataset_id: str, version: int | None = None) -> DatasetInspection:
        validate_dataset_id(dataset_id)
        if version is not None and (type(version) is not int or version < 1):
            raise DomainError("INVALID_INPUT", "Version must be a positive integer.")
        record, contract = self.store.get(dataset_id, version)
        table = decode_snapshot(
            record["snapshot"], record["snapshot_sha256"], contract, record["row_count"]
        )
        return DatasetInspection(
            dataset_id=dataset_id,
            version=record["version"],
            row_count=table.num_rows,
            column_count=len(contract.columns),
            contract_sha256=contract.sha256,
            source_sha256=record["source_sha256"],
            snapshot_sha256=record["snapshot_sha256"],
            source_format=record["source_format"],
            contract=contract,
            columns=[
                ColumnProfile(
                    name=c.name, dtype=str(table[c.name].type), null_count=table[c.name].null_count
                )
                for c in contract.columns
            ],
        )
