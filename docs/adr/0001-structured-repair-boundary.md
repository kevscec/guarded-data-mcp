# ADR-0001: Restrict agent execution to structured repair operations

## Status

Accepted by Kevin Ceciliano Gamboa during project discovery. This records a design decision, not an implemented capability.

## Date

2026-11-13

## Context

An analyst needs help investigating and repairing a local dataset. The MCP server must let an agent propose consequential changes while keeping the permitted effects explainable and testable. Similar records are not necessarily duplicates, and unexpected values are not necessarily incorrect.

The project must demonstrate deliberate tool design, least privilege, typed outputs, failure handling and evaluation. A general code executor would make its effective repair surface much larger than its documented tools.

## Options Considered

1. **Arbitrary SQL or Python.** Supports open-ended analysis and transformations, but makes effect validation and isolation significantly harder.
2. **Structured operations under an approved contract.** Constrains effects and enables exact outcome checks, but requires extending the implementation for new transformations.
3. **Read-only diagnosis.** Avoids mutation risk, but does not deliver repairs or demonstrate control of consequential operations.

## Decision

We choose structured inspection and repair operations, without arbitrary SQL, Python or free-form executable expressions in tool arguments.

A versioned, human-approved dataset contract defines record identity and quality rules. The agent may propose contract or mapping changes, but cannot activate them itself or weaken the rules while repairing data.

The initial repair families are:

- **Exact deduplication:** retain one occurrence when a contract declares a key unique and all record values match. A shared key with different values is an unresolved conflict, not permission to choose a winner.
- **Explicit normalization:** apply approved equivalences. Do not invent missing values or infer a replacement merely because it looks plausible.
- **Quarantine:** separate records that violate explicit rules while preserving their content and reasons. Quarantine is not proof of a successful correction.

Each tool returns structured, typed results. The model investigates, selects and explains a proposal; the server validates and executes its permitted effects.

## Consequences

- New repair families require explicit contracts, implementation and evaluations; the agent cannot improvise unsupported transformations.
- Unresolved conflicts may remain after a successful repair. Reports must distinguish execution success from complete data quality.
- Query filters, rule definitions and mappings need bounded, non-executable schemas; refusing arbitrary code at the top level is insufficient if another field becomes an interpreter.
- Deduplication tests must preserve legitimate repeated records when no approved unique-key rule applies.

## Related Decisions

- [ADR-0002](0002-atomic-state-bound-plans.md): approval and execution guarantees.
- [ADR-0003](0003-use-registered-local-datasets.md): dataset scope and human workflow.
- [ADR-0004](0004-expose-six-mcp-tools.md): agent-facing tool surface.

## Record History

Expanded from the initial short decision note on 2026-11-13. Its original restriction on arbitrary code and independent human approval remains unchanged.
