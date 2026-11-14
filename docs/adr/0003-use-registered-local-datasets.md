# ADR-0003: Operate on registered local single-table datasets

## Status

Accepted by Kevin Ceciliano Gamboa during project discovery.

## Date

2026-11-13

## Context

The primary user is an analyst preparing data for analysis. The product needs a complete local demonstration and reusable behavior, with a smaller permission surface than unrestricted filesystem or production-database access. Scope is defined by requirements and a development plan, not a calendar limit.

## Options Considered

1. **Connect to external databases and repair related tables.** Covers broader operational workflows, but introduces credentials, ownership, relationships and upstream availability into the repair boundary.
2. **Manage registered local datasets.** Supports reproducible execution and explicit access scope, but requires import/export and copies of data.
3. **Build a dataset-specific repair script.** Has simpler rules, but does not establish a reusable server and tool contract.

## Decision

We choose a reusable engine with one table per dataset and multiple independently registered datasets. Preserve the original source and apply approved repairs to a persistent managed working copy.

The human uses a CLI to import CSV or Parquet, review and activate versioned contracts/mappings, review and approve exact plans, and export a selected committed version. The agent operates on registered dataset identifiers, without arbitrary local paths. The example dataset's rules belong in its contract rather than in server-specific business logic.

Every working-data mutation initially requires human approval. Approval is a separate human CLI action, not an MCP capability available to the agent. Contract changes and data repairs are separate decisions.

Exports include provenance, contract version, repair counts, quarantine reasons, unresolved findings and verification results. CSV and Parquet are the initial supported formats. Exporting files is a human operation, distinct from committing a repair.

The declared adversary is an agent limited to the exposed MCP capabilities. The human operator, server implementation and host operating system are trusted. This boundary does not constrain an agent with unrestricted shell or filesystem access merely because approval uses a different terminal.

## Consequences

- No initial cross-table repair, external database synchronization, Excel import, URL ingestion or unrestricted filesystem tools.
- Import preserves source bytes and provenance; codecs must distinguish text identifiers, nulls, empty strings and declared date/number semantics.
- CLI and server access to shared state require a concurrency design; separate processes must not invalidate approval or atomicity guarantees.
- A source backup does not excuse an incorrect working-data repair. Correctness and collateral-change checks remain required.
- A UI, multi-user service and public hosting are not initial requirements. Deployment can be revisited if it serves the problem.

## Related Decisions

- [ADR-0001](0001-structured-repair-boundary.md): reusable repair families.
- [ADR-0002](0002-atomic-state-bound-plans.md): mutation and restoration guarantees.
- [ADR-0004](0004-expose-six-mcp-tools.md): agent capabilities.
- [ADR-0006](0006-pin-public-demo-and-synthetic-defects.md): public example and source provenance.
