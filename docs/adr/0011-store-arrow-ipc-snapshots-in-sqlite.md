# ADR-0011: Encode complete data versions as Arrow IPC blobs in SQLite

## Status

Accepted implementation decision for the authorized M1 scope under ADR-0008 and ADR-0010. The encoding is validated by the M1 round-trip and protocol tests; this is not a claim that future repair execution is implemented.

## Date

2026-11-13

## Context

The accepted architecture requires complete versions inside a single authoritative SQLite database, with faithful scalar values. SQLite affinities alone do not preserve exact decimals, timestamp units/timezones or signed floating-point zero. The initial dataset size is explicitly bounded.

## Options Considered

1. **Native SQLite columns with custom scalar codecs.** Enables SQL row selection, but requires a second physical type mapping and explicit encoding for decimal/time/float details.
2. **Arrow IPC blobs inside SQLite.** Retains the declared Arrow types and raw float bits while sharing SQLite transactions with metadata; inspecting individual rows requires decoding a bounded snapshot.
3. **External Arrow/Parquet files with SQLite references.** Avoids large database blobs, but introduces a cross-store publication/recovery mechanism rejected for the initial scope.

## Decision

We use uncompressed Arrow IPC file-format blobs for complete active and quarantine states in SQLite STRICT tables. Preserve source bytes in a separate content-addressed BLOB and canonical contract JSON by SHA-256. Versions reference the original source and contract hashes.

Append an internal positive int64 occurrence ID (`_gdm_row_id`) to each imported row. Its initial value is source order starting at one; it is independent of business keys and cannot collide with user columns because the `_gdm_` namespace is reserved. Do not use business uniqueness constraints to reject or collapse input duplicates.

Before inspection, verify the stored snapshot and contract hashes and the decoded shape/schema/occurrence IDs. Do not coerce unsupported Parquet schemas into matching types. Initial decimal support is decimal128 with precision 1–38 and scale 0–precision. Timestamps require an explicit unit; supported timezone forms are naive and UTC. More timezone forms require explicit codec validation.

CSV uses a documented UTF-8 comma/header dialect. An unquoted `\N` is null; quoted `"\N"` is literal text; an empty text field is empty text. Non-text empty values must match their declared type or fail. Nullability is retained as a quality requirement for M2; import preserves nulls instead of dropping offending rows.

## Consequences

- Read handlers decode snapshots rather than issuing user-generated row SQL. This is acceptable within the bounded initial envelope, not an analytical throughput claim.
- Source bytes, contract, complete version and registration commit together. Database schema initialization is a separate short transaction; rejected imports may leave an empty initialized workspace but no partial dataset/source/contract registration.
- Logical retained-content quota includes sources, contract JSON and snapshot/quarantine blobs. SQLite/journal overhead is separate from that quota.
- Streaming batches bound accumulated rows/cells/logical bytes, but native decoder allocations and cooperative deadlines are not an OS memory/CPU sandbox for malicious files. The human supplies files; a later hostile-file threat model needs process-level limits.
- M1 exposes null profiles and provenance, not quality findings or repair tools. Required-field/unique-key rules are not falsely reported as evaluated.
- Changing the version encoding requires a migration and new round-trip evidence; IPC bytes are not assumed stable across library upgrades.

## Related Decisions

- [ADR-0008](0008-use-sqlite-and-pyarrow.md): one authoritative database.
- [ADR-0009](0009-use-closed-rules-and-explicit-scalar-types.md): typed semantics.
- [ADR-0010](0010-retain-complete-versions-with-bounds.md): complete versions and bounds.

## References

- [Codec implementation](../../src/guarded_data_mcp/codec.py).
- [Storage implementation](../../src/guarded_data_mcp/storage.py).
- [Behavior/failure tests](../../tests/test_import.py).
