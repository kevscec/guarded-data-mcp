# ADR-0004: Expose six tools for investigation and controlled execution

## Status

Accepted by Kevin Ceciliano Gamboa during project discovery. Names and responsibilities are accepted; exact schemas, limits and transport are not yet selected.

Later resolution: [ADR-0007](0007-use-python-and-mcp-stdio.md) selects Python, the official SDK and stdio. Exact tool schemas and limits remain specification work.

## Date

2026-11-13

## Context

The server should expose a deliberate tool surface that guides investigation, review and execution without granting the agent human authority. It must also let the agent reconcile an uncertain execution outcome.

## Options Considered

1. **Expose low-level storage CRUD.** Flexible, but permits bypassing the review lifecycle and shifts policy into prompts.
2. **One universal action tool.** Reduces tool count, but combines unrelated privileges and makes discoverability and validation less clear.
3. **Six tools with distinct responsibilities.** Makes the workflow explicit, but requires several calls and careful output bounds.

## Decision

We choose the following six agent-facing tools:

| Tool | Responsibility |
| --- | --- |
| `list_datasets` | Discover available registered datasets. |
| `inspect_dataset` | Inspect an approved contract, versions, data profile and detected problems. |
| `query_records` | Investigate records through structured filters and bounded results. |
| `prepare_plan` | Simulate and persist an exact repair or restoration proposal. |
| `get_plan` | Read proposal, approval state, execution state and persisted result. |
| `apply_plan` | Execute the exact approved plan without accepting altered instructions. |

There is no MCP tool to approve a plan, activate a contract, import arbitrary paths or export to arbitrary paths. Those are human CLI responsibilities.

Structured results must distinguish findings, unresolved conflicts, execution outcome and insufficient/incomplete evidence. Bounded samples must not be represented as full-dataset validation. Domain refusals must be machine-recognizable rather than successful prose containing the word "error".

## Consequences

- Tool descriptions must explain prerequisites, permitted effects and recovery steps; tool count alone is not the design objective.
- `prepare_plan` writes plan metadata even when it does not mutate working rows. Future MCP annotations must describe its actual behavior.
- `get_plan` is required for lost-response recovery, not only for presenting a preview.
- Exact filter/rule schemas, pagination, result limits, error codes, SDK version and transport need a subsequent technical decision before implementation.
- Automatic quality claims cannot be inferred from successful calls. Actual dataset state is an evaluation oracle.

## Related Decisions

- [ADR-0001](0001-structured-repair-boundary.md): typed, non-executable operations.
- [ADR-0002](0002-atomic-state-bound-plans.md): plan lifecycle and replay.
- [ADR-0003](0003-use-registered-local-datasets.md): CLI and trust boundary.
- [ADR-0005](0005-evaluate-server-and-real-agent.md): protocol and outcome evaluations.
