# ADR-0012: Version quality contracts separately from immutable data

## Status

Accepted M2 implementation decision within the authorized contract-activation scope. This records implementation trade-offs, not an independent architecture review.

## Date

2026-11-13

## Context

An analyst can approve new quality rules without repairing any records. Overwriting a version's import contract would change its provenance. Reverting to an earlier contract must not revive old cursors or, later, approvals. M1 already publishes content-addressed schema-v1 contracts.

## Options Considered

1. **Overwrite the version contract.** Simple reads, but changes immutable provenance and cannot distinguish reactivation from an unchanged state.
2. **Create a complete data version on every rule activation.** Uniform history, but duplicates snapshots for a metadata-only change and confuses data publication with rule review.
3. **Append contract activations with monotonically increasing revisions.** Preserves source/version provenance and makes state changes explicit, at the cost of a second history and a schema migration.

## Decision

We append human-only activations transactionally and keep each data version's physical import contract unchanged. Inspection and queries evaluate the requested immutable data version under the explicitly returned current quality contract and head revision. Activation cannot change names, order or physical scalar types. Nullability, keys, rules and finite normalization maps may change after review; activating a map never applies it.

Contract schema v2 adds closed rules/maps. Schema v1 canonical bytes and hashes remain unchanged. SQLite schema v2 adds activation history; only a human write migrates schema v1, transactionally. Read-only MCP sessions support both formats without silently migrating.

Cursors use a process-local HMAC key and bind dataset, data version, revision, snapshot, contract and full query identity. They expire on server restart. Findings bind the same reviewed state. We choose restart expiry over persistent signing-key lifecycle or server-written cursor state because investigation is read-only and restarting pagination is inexpensive.

## Consequences

- Contract changes invalidate old evidence references even when reactivating identical content.
- Historical data is inspectable under current rules, with physical and active contract hashes separately visible; this is not historical-rule replay.
- MCP cannot activate contracts or write migrations. Full scans return complete counts or an error; evidence remains bounded.
- Future repair publication must advance this same head revision in its atomic transaction. M2 does not implement publication or approvals.
- Human activation and initial import preflight analysis/result bounds before publication. Oversized inspection contracts are refused rather than made unreadable through MCP.

## Related Decisions

- [ADR-0002](0002-atomic-state-bound-plans.md): state-bound plans.
- [ADR-0009](0009-use-closed-rules-and-explicit-scalar-types.md): approved rule/type vocabulary.
- [ADR-0011](0011-store-arrow-ipc-snapshots-in-sqlite.md): immutable physical snapshots.
