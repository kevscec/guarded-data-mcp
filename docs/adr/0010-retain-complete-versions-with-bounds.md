# ADR-0010: Retain complete versions within an explicit initial envelope

## Status

Accepted by Kevin Ceciliano Gamboa in response to Q28. Auxiliary operational defaults remain identified separately in the technical specification.

## Date

2026-11-13

## Context

Recovery, exact previews and historical evaluation need reproducible states. A delta-based store can save disk but adds reconstruction and retention complexity. The initial version needs an honest, testable supported scope rather than an unlimited-scale claim.

## Options Considered

1. **Store deltas and reconstruct history.** Uses less space for small changes, but complicates recovery, integrity and version reconstruction.
2. **Retain complete immutable versions.** Simplifies recovery and whole-state checks, but grows with dataset size and version count.
3. **Keep only the current state and source.** Minimizes history storage, but cannot provide the accepted intermediate-version restoration and evidence.

## Decision

We choose complete immutable versions within SQLite for the initial implementation, including active data and quarantine state. Keep published history without automatic pruning. Refuse new writes when the configured quota would be exceeded; never reclaim history silently.

Initial combined input ceilings are 100,000 rows, 100 columns, 1,000,000 cells and 64 MiB per source file. All ceilings apply, so a 100-column dataset may reach the cell ceiling before the row ceiling. These are acceptance limits to verify, not measured throughput or latency claims.

The human may lower limits. Raising supported scale requires benchmarks and evaluation of data integrity, capacity and recovery before expanding the published claim.

## Consequences

- Quota accounting includes retained sources, data versions, quarantine and plan artifacts; physical SQLite/journal overhead must be measured separately.
- Additional limits for response size, operation duration and lock waits are implementation defaults to validate, not consequences of the row ceiling alone.
- Large files, unsupported datasets and exhausted storage receive explicit refusals without partial publication.
- Automatic pruning, compaction policies and delta storage are future decisions with their own history/recovery trade-offs.

## Related Decisions

- [ADR-0002](0002-atomic-state-bound-plans.md): versioned restoration and receipts.
- [ADR-0008](0008-use-sqlite-and-pyarrow.md): authoritative SQLite store.
- [ADR-0009](0009-use-closed-rules-and-explicit-scalar-types.md): supported logical values.
