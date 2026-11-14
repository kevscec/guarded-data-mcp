# ADR-0008: Keep authoritative state in SQLite and use PyArrow for interchange

## Status

Accepted by Kevin Ceciliano Gamboa in response to Q25. Physical schema, codecs and scale limits require specification before implementation.

Later resolution: [ADR-0009](0009-use-closed-rules-and-explicit-scalar-types.md) selects logical scalar types and [ADR-0010](0010-retain-complete-versions-with-bounds.md) selects complete versions and the initial input ceilings. Physical codecs remain technical validation work.

## Date

2026-11-13

## Context

Applying a plan must coordinate working data, quarantine, version history, approval consumption and its durable receipt. The human CLI and stdio server are separate processes. CSV/Parquet interoperability must preserve declared types rather than treating inferred values as an approved contract.

## Options Considered

1. **One authoritative SQLite database and PyArrow adapters.** Supports cross-process connections and a shared transaction for the critical state; has one writer at a time and needs explicit logical type codecs.
2. **Embedded DuckDB for all state.** Offers rich analytical types, but its embedded write model does not directly fit independent CLI/server writers without centralizing writes or adding a service.
3. **Parquet working files plus SQLite metadata.** Keeps interchange files directly accessible, but adds a cross-store publication/recovery protocol because filesystem changes and SQLite updates do not share one transaction.

## Decision

We choose SQLite as the single authoritative store for working-data versions, quarantine and control metadata. Use PyArrow for CSV/Parquet import and export. Exported files are derivative artifacts, not an independently authoritative working store.

Application must check the approved state and publish data/version, quarantine state, consumed approval and unique plan receipt within one database transaction. A completed plan returns its existing receipt on replay. Concurrent calls must be serialized or refused with an explicit bounded lock error, not silently overwrite a newer version.

The intended persistence pattern is explicit transactions, connection-specific foreign-key checks, local-disk WAL and deliberate synchronization settings. Verify their behavior with separate CLI/server processes. Never hold a write transaction open while waiting for a person to review a plan.

SQLite physical types do not themselves define the logical dataset schema. Codecs must preserve text identifiers, null versus empty text, exact decimal semantics and declared date/time precision and timezone behavior. Unsupported or lossy conversions are refused rather than silently accepted.

## Consequences

- Storage and transaction code must be centralized; domain operations cannot publish state by writing their own external working files.
- PyArrow is an interchange dependency, not a second database. Explicit schemas and CSV null policies must accompany import/export.
- One writer is acceptable for the accepted local, single-user workflow. Busy handling, capacity limits and retention behavior require explicit specification and tests.
- Durability depends on the local OS/filesystem honoring locking and synchronization; do not claim protection from every hardware or filesystem failure.
- Full-version storage versus another physical representation remains a proposed detail in the technical specification, not an accepted choice by implication.

## Related Decisions

- [ADR-0002](0002-atomic-state-bound-plans.md): atomicity and replay invariants.
- [ADR-0003](0003-use-registered-local-datasets.md): independent CLI and agent responsibilities.
- [ADR-0007](0007-use-python-and-mcp-stdio.md): runtime and process architecture.

## References

- [SQLite transactions](https://www.sqlite.org/lang_transaction.html).
- [SQLite WAL](https://www.sqlite.org/wal.html).
- [SQLite data types](https://www.sqlite.org/datatype3.html).
- [DuckDB concurrency](https://www.duckdb.org/docs/current/connect/concurrency).
- [PyArrow CSV](https://arrow.apache.org/docs/python/csv.html).
