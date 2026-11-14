"""Single authoritative SQLite boundary, including immutable source and Arrow versions."""

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from guarded_data_mcp.domain import DEFAULT_LIMITS, Contract, DomainError, Limits

APPLICATION_ID = 0x47444D31
SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    sha256 TEXT PRIMARY KEY, content BLOB NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS contracts (
    sha256 TEXT PRIMARY KEY, document TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY, current_version INTEGER NOT NULL,
    FOREIGN KEY(dataset_id, current_version) REFERENCES versions(dataset_id, version)
        DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE IF NOT EXISTS versions (
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id), version INTEGER NOT NULL,
    source_sha256 TEXT NOT NULL REFERENCES sources(sha256),
    contract_sha256 TEXT NOT NULL REFERENCES contracts(sha256),
    snapshot BLOB NOT NULL, snapshot_sha256 TEXT NOT NULL,
    quarantine BLOB NOT NULL, row_count INTEGER NOT NULL CHECK(row_count >= 0),
    column_count INTEGER NOT NULL CHECK(column_count > 0),
    source_format TEXT NOT NULL CHECK(source_format IN ('csv','parquet')),
    created_at TEXT NOT NULL,
    PRIMARY KEY(dataset_id, version)
) STRICT;
"""


class Store:
    def __init__(self, workspace: Path, limits: Limits = DEFAULT_LIMITS):
        self.path = workspace.resolve() / "guarded-data.sqlite3"
        self.limits = limits

    @contextmanager
    def connection(self, *, write: bool = False):
        connection = None
        try:
            if write:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                self.path.as_uri() + ("?mode=rwc" if write else "?mode=ro"),
                uri=True,
                timeout=self.limits.lock_seconds,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if write and application_id == 0 and version == 0:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("BEGIN IMMEDIATE")
                # Another CLI may have initialized while this connection waited for the lock.
                header = (
                    connection.execute("PRAGMA application_id").fetchone()[0],
                    connection.execute("PRAGMA user_version").fetchone()[0],
                )
                if header == (0, 0):
                    if connection.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]:
                        raise DomainError("STORAGE_INTEGRITY", "Unknown workspace database.")
                    for statement in SCHEMA.split(";"):
                        if statement.strip():
                            connection.execute(statement)
                    connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                    connection.execute("PRAGMA user_version=1")
                elif header != (APPLICATION_ID, 1):
                    raise DomainError("STORAGE_INTEGRITY", "Unsupported workspace database format.")
                connection.commit()
            elif application_id != APPLICATION_ID or version != 1:
                raise DomainError("STORAGE_INTEGRITY", "Unsupported workspace database format.")
            if write:
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("BEGIN IMMEDIATE")
            else:
                connection.execute("PRAGMA query_only=ON")
                connection.execute("BEGIN")
            yield connection
            if write:
                connection.commit()
        except sqlite3.OperationalError as exc:
            busy = (getattr(exc, "sqlite_errorcode", 0) & 0xFF) in (
                sqlite3.SQLITE_BUSY,
                sqlite3.SQLITE_LOCKED,
            )
            raise DomainError(
                "STORAGE_BUSY" if busy else "STORAGE_UNAVAILABLE",
                "Workspace is busy; retry later."
                if busy
                else "Workspace database could not be accessed.",
                retryable=busy,
            ) from exc
        except sqlite3.DatabaseError as exc:
            raise DomainError(
                "STORAGE_INTEGRITY", "Workspace database failed integrity checks."
            ) from exc
        except OSError as exc:
            raise DomainError("STORAGE_UNAVAILABLE", "Workspace storage is unavailable.") from exc
        finally:
            if connection is not None:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

    def register(
        self,
        dataset_id: str,
        raw: bytes,
        contract: Contract,
        source_format: str,
        blob: bytes,
        quarantine: bytes,
        rows: int,
    ) -> None:
        source_hash = hashlib.sha256(raw).hexdigest()
        document = contract.canonical_json()
        with self.connection(write=True) as connection:
            if connection.execute(
                "SELECT 1 FROM datasets WHERE dataset_id=?", (dataset_id,)
            ).fetchone():
                raise DomainError(
                    "DATASET_EXISTS", "Dataset ID is already registered; nothing changed."
                )
            used = connection.execute("""SELECT
                (SELECT coalesce(sum(length(content)),0) FROM sources) +
                (SELECT coalesce(sum(length(CAST(document AS BLOB))),0) FROM contracts) +
                (SELECT coalesce(sum(length(snapshot)+length(quarantine)),0) FROM versions)
                """).fetchone()[0]
            source = connection.execute(
                "SELECT content FROM sources WHERE sha256=?", (source_hash,)
            ).fetchone()
            stored_contract = connection.execute(
                "SELECT document FROM contracts WHERE sha256=?", (contract.sha256,)
            ).fetchone()
            if (source is not None and source[0] != raw) or (
                stored_contract is not None and stored_contract[0] != document
            ):
                raise DomainError(
                    "STORAGE_INTEGRITY", "Content-addressed source/contract is damaged."
                )
            new_source = source is None
            new_contract = stored_contract is None
            additional = len(blob) + len(quarantine) + (len(raw) if new_source else 0)
            additional += len(document.encode()) if new_contract else 0
            if used + additional > self.limits.quota_bytes:
                raise DomainError(
                    "RESOURCE_LIMIT", "Import would exceed the retained-content quota."
                )
            connection.execute("INSERT OR IGNORE INTO sources VALUES (?,?)", (source_hash, raw))
            connection.execute(
                "INSERT OR IGNORE INTO contracts VALUES (?,?)", (contract.sha256, document)
            )
            connection.execute("INSERT INTO datasets VALUES (?,1)", (dataset_id,))
            connection.execute(
                "INSERT INTO versions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    dataset_id,
                    1,
                    source_hash,
                    contract.sha256,
                    blob,
                    hashlib.sha256(blob).hexdigest(),
                    quarantine,
                    rows,
                    len(contract.columns),
                    source_format,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def list(self, limit: int, after: str | None) -> list[dict]:
        if not self.path.exists():
            return []
        with self.connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """
                SELECT d.dataset_id,v.version,v.row_count,v.column_count
                FROM datasets d JOIN versions v
                  ON d.dataset_id=v.dataset_id AND d.current_version=v.version
                WHERE d.dataset_id > ? ORDER BY d.dataset_id LIMIT ?
                """,
                    (after or "", limit),
                )
            ]

    def get(self, dataset_id: str, version: int | None) -> tuple[dict, Contract]:
        if not self.path.exists():
            raise DomainError("UNKNOWN_DATASET", "No dataset is registered with that ID.")
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT v.*,c.document FROM datasets d JOIN versions v
                    ON v.dataset_id=d.dataset_id AND v.version=coalesce(?,d.current_version)
                    JOIN contracts c ON c.sha256=v.contract_sha256
                WHERE d.dataset_id=?
                """,
                (version, dataset_id),
            ).fetchone()
            if row is None:
                if not connection.execute(
                    "SELECT 1 FROM datasets WHERE dataset_id=?", (dataset_id,)
                ).fetchone():
                    raise DomainError("UNKNOWN_DATASET", "No dataset is registered with that ID.")
                raise DomainError(
                    "UNKNOWN_DATASET_VERSION", "Dataset or requested version is not registered."
                )
            result = dict(row)
            try:
                contract = Contract.model_validate_json(result["document"])
            except ValidationError as exc:
                raise DomainError("STORAGE_INTEGRITY", "Stored contract is invalid.") from exc
            if contract.sha256 != result["contract_sha256"]:
                raise DomainError("STORAGE_INTEGRITY", "Stored contract checksum does not match.")
            return result, contract
