"""Single authoritative SQLite boundary, including immutable source and Arrow versions."""

import hashlib
import sqlite3
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from guarded_data_mcp.domain import DEFAULT_LIMITS, Contract, DomainError, Limits, PlanDocument

APPLICATION_ID = 0x47444D31
# ADR-0012: metadata revisions never rewrite a version's physical import contract.
ACTIVATIONS = """CREATE TABLE IF NOT EXISTS activations (
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    revision INTEGER NOT NULL CHECK(revision > 0),
    contract_sha256 TEXT NOT NULL REFERENCES contracts(sha256),
    created_at TEXT NOT NULL, PRIMARY KEY(dataset_id,revision)
) STRICT"""
PLANS = """CREATE TABLE IF NOT EXISTS plans (
    plan_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    document TEXT NOT NULL, active_preview BLOB NOT NULL, quarantine_preview BLOB NOT NULL,
    created_at TEXT NOT NULL
) STRICT"""
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
    def connection(self, *, write: bool = False, migrate: bool = True):
        connection = None
        try:
            if write and migrate:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                self.path.as_uri()
                + ("?mode=rwc" if write and migrate else "?mode=rw" if write else "?mode=ro"),
                uri=True,
                timeout=self.limits.lock_seconds,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN")
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            connection.rollback()
            if write and migrate and application_id == 0 and version == 0:
                # Journal-mode lock upgrades can return BUSY immediately without invoking
                # SQLite's busy handler when another initializer briefly holds a read lock.
                # Retry only this pre-transaction setup, within the same bounded lock budget.
                deadline = time.monotonic() + self.limits.lock_seconds
                while True:
                    try:
                        connection.execute("PRAGMA journal_mode=WAL")
                        break
                    except sqlite3.OperationalError as exc:
                        if (getattr(exc, "sqlite_errorcode", 0) & 0xFF) not in (
                            sqlite3.SQLITE_BUSY,
                            sqlite3.SQLITE_LOCKED,
                        ) or time.monotonic() >= deadline:
                            raise
                        time.sleep(min(0.01, max(0, deadline - time.monotonic())))
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
                elif header not in ((APPLICATION_ID, 1), (APPLICATION_ID, 2), (APPLICATION_ID, 3)):
                    raise DomainError("STORAGE_INTEGRITY", "Unsupported workspace database format.")
                connection.commit()
            elif application_id != APPLICATION_ID or version not in (1, 2, 3):
                raise DomainError("STORAGE_INTEGRITY", "Unsupported workspace database format.")
            if write:
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("BEGIN IMMEDIATE")
                schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
                if not migrate and schema_version != 3:
                    raise DomainError(
                        "WORKSPACE_UPGRADE_REQUIRED",
                        "Run the human CLI workspace-upgrade command before preparing plans.",
                    )
                if schema_version == 1:
                    connection.execute(ACTIVATIONS)
                    connection.execute("""INSERT INTO activations
                        SELECT d.dataset_id,1,v.contract_sha256,v.created_at
                        FROM datasets d JOIN versions v ON d.dataset_id=v.dataset_id
                        AND d.current_version=v.version""")
                    connection.execute("PRAGMA user_version=2")
                if migrate and schema_version < 3:
                    connection.execute(PLANS)
                    connection.execute("PRAGMA user_version=3")
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
            used = self.used_bytes(connection)
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
            connection.execute(
                "INSERT INTO activations VALUES (?,1,?,?)",
                (dataset_id, contract.sha256, datetime.now(UTC).isoformat()),
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
            result["head_revision"] = 1
            result["active_document"] = result["document"]
            result["active_contract_sha256"] = contract.sha256
            if connection.execute("PRAGMA user_version").fetchone()[0] >= 2:
                activation = connection.execute(
                    """SELECT a.revision,a.contract_sha256,c.document
                    FROM activations a JOIN contracts c ON c.sha256=a.contract_sha256
                    WHERE a.dataset_id=? ORDER BY a.revision DESC LIMIT 1""",
                    (dataset_id,),
                ).fetchone()
                if activation is None:
                    raise DomainError("STORAGE_INTEGRITY", "Active contract is missing.")
                result.update(
                    head_revision=activation["revision"],
                    active_document=activation["document"],
                    active_contract_sha256=activation["contract_sha256"],
                )
            return result, contract

    def activate(self, dataset_id: str, contract: Contract, expected_revision: int) -> int:
        with self.connection(write=True) as connection:
            row = connection.execute(
                """SELECT a.revision,c.document FROM activations a
                JOIN contracts c ON c.sha256=a.contract_sha256
                WHERE a.dataset_id=? ORDER BY a.revision DESC LIMIT 1""",
                (dataset_id,),
            ).fetchone()
            if row is None:
                raise DomainError("UNKNOWN_DATASET", "No dataset is registered with that ID.")
            if row["revision"] != expected_revision:
                raise DomainError("STALE_REVISION", "Reviewed dataset revision has changed.")
            old = Contract.model_validate_json(row["document"])
            if [c.model_dump(exclude={"nullable"}) for c in old.columns] != [
                c.model_dump(exclude={"nullable"}) for c in contract.columns
            ]:
                raise DomainError("SCHEMA_CHANGE", "Activation cannot change the physical schema.")
            document = contract.canonical_json()
            stored = connection.execute(
                "SELECT document FROM contracts WHERE sha256=?", (contract.sha256,)
            ).fetchone()
            if stored is not None and stored[0] != document:
                raise DomainError("STORAGE_INTEGRITY", "Stored contract is damaged.")
            if stored is None:
                used = self.used_bytes(connection)
                if used + len(document.encode()) > self.limits.quota_bytes:
                    raise DomainError("RESOURCE_LIMIT", "Contract would exceed retained quota.")
                connection.execute(
                    "INSERT INTO contracts VALUES (?,?)", (contract.sha256, document)
                )
            revision = expected_revision + 1
            connection.execute(
                "INSERT INTO activations VALUES (?,?,?,?)",
                (dataset_id, revision, contract.sha256, datetime.now(UTC).isoformat()),
            )
            return revision

    @staticmethod
    def used_bytes(connection) -> int:
        return connection.execute("""SELECT
            (SELECT coalesce(sum(length(content)),0) FROM sources) +
            (SELECT coalesce(sum(length(CAST(document AS BLOB))),0) FROM contracts) +
            (SELECT coalesce(sum(length(snapshot)+length(quarantine)),0) FROM versions) +
            (SELECT coalesce(sum(length(CAST(document AS BLOB)) + length(active_preview)
                + length(quarantine_preview)),0) FROM plans)
            """).fetchone()[0]

    def upgrade(self) -> dict:
        with self.connection(write=True) as connection:
            return {
                "status": "ok",
                "workspace_schema": connection.execute("PRAGMA user_version").fetchone()[0],
            }

    def save_plan(
        self, plan: PlanDocument, active: bytes, quarantine: bytes, deadline: float
    ) -> None:
        from guarded_data_mcp.quality import deadline_check

        document = plan.canonical_json()
        with self.connection(write=True, migrate=False) as connection:
            deadline_check(deadline)
            binding = plan.binding
            current = connection.execute(
                """SELECT d.current_version,v.snapshot_sha256,v.snapshot,
                v.quarantine,a.revision,a.contract_sha256 FROM datasets d JOIN versions v
                ON v.dataset_id=d.dataset_id AND v.version=d.current_version
                JOIN activations a ON a.dataset_id=d.dataset_id WHERE d.dataset_id=?
                ORDER BY a.revision DESC LIMIT 1""",
                (binding.dataset_id,),
            ).fetchone()
            if current is None or (
                current["current_version"],
                current["revision"],
                current["contract_sha256"],
                current["snapshot_sha256"],
                hashlib.sha256(current["quarantine"]).hexdigest(),
            ) != (
                binding.version,
                binding.head_revision,
                binding.contract_sha256,
                binding.snapshot_sha256,
                binding.quarantine_sha256,
            ):
                raise DomainError(
                    "STALE_REVISION", "Dataset state changed during plan preparation."
                )
            if hashlib.sha256(current["snapshot"]).hexdigest() != binding.snapshot_sha256:
                raise DomainError("STORAGE_INTEGRITY", "Base snapshot is damaged.")
            existing = connection.execute(
                "SELECT document,active_preview,quarantine_preview FROM plans WHERE plan_id=?",
                (plan.plan_id,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) != (document, active, quarantine):
                    raise DomainError("STORAGE_INTEGRITY", "Persisted plan content is damaged.")
                return
            additional = len(document.encode()) + len(active) + len(quarantine)
            if self.used_bytes(connection) + additional > self.limits.quota_bytes:
                raise DomainError("RESOURCE_LIMIT", "Plan would exceed retained-content quota.")
            connection.execute(
                "INSERT INTO plans VALUES (?,?,?,?,?,?)",
                (
                    plan.plan_id,
                    binding.dataset_id,
                    document,
                    active,
                    quarantine,
                    datetime.now(UTC).isoformat(),
                ),
            )
            deadline_check(deadline)

    def read_plan(self, plan_id: str) -> dict:
        if not self.path.exists():
            raise DomainError("UNKNOWN_PLAN", "Plan is not registered.")
        with self.connection() as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] < 3:
                raise DomainError("UNKNOWN_PLAN", "No plans exist in this workspace format.")
            row = connection.execute("SELECT * FROM plans WHERE plan_id=?", (plan_id,)).fetchone()
            if row is None:
                raise DomainError("UNKNOWN_PLAN", "Plan is not registered.")
            return dict(row)
