# ADR-0013: Persist exact simulated proposals before approval exists

## Status

Accepted M3 implementation decision within the authorized immutable-proposal scope. Approval and publication remain M4 work; no independent architecture review is claimed.

## Date

2026-11-13

## Context

An ordered repair preview must expose combined effects without changing the working data. Repeating a timed-out preparation or restarting the server must recover the same proposal. Recomputing later against a changed contract could produce a different result from the one a human reviewed.

## Options Considered

1. **Persist instructions and recompute every review.** Small storage footprint, but review depends on current algorithms/state and does not independently freeze the predicted output.
2. **Persist an occurrence manifest only.** Audits affected identities, but requires replay to inspect the complete typed output and quarantine.
3. **Persist the canonical document, exact occurrence effects and typed preview blobs.** Freezes both instructions and results, with higher storage cost and a bounded manifest.

## Decision

We choose a content-addressed immutable document plus complete Arrow IPC active/quarantine previews in SQLite. The document freezes the current data version, head revision, contract (including maps), snapshot/quarantine hashes, ordered request, exact effects and full-scan findings. Its canonical SHA-256 defines the plan ID; creation time is separate. Identical preparation at the same state recovers the same plan. No approval or execution capability exists in M3.

Simulation uses active approved finite maps once per normalization step; key changes require explicit intent. Deduplication retains the smallest occurrence ID only in complete-key groups whose entire records are identical. Quarantine names a current step rule/kind and exact IDs, preserves their typed values at that stage, and records a server-derived reason for each occurrence.

Mandatory postconditions conserve occurrence identities and types and forbid new final rule violations: each final `(rule ID, kind)` occurrence set must be a subset of its original set. Existing unresolved findings remain visible. Intermediate violations are permitted only when resolved later in the same ordered plan. This conservative default rejects a normalization-only plan that creates duplicates or conflicts; it never guesses which conflicting record is correct.

Saving a proposal rechecks the bound state inside the same transaction as its insert. A timeout, stale state, failed step/postcondition or quota failure persists no partial proposal. SQLite schema v3 adds proposals; imports, activations or explicit human `workspace-upgrade` migrate. MCP preparation refuses an old format instead of migrating it.

## Consequences

- Preparation writes metadata/previews, so its MCP read-only annotation is false. It publishes no version or quarantine changes.
- Retained-content quota includes all proposal documents/blobs. Limits are 20 steps, 100,000 effect entries and 16 MiB canonical document, plus existing data/result ceilings. These are capacity bounds, not performance claims.
- `get_plan` paginates the immutable exact manifest and marks stale state without rewriting it. Human `review-plan` exposes the complete frozen contract/request/document. Plan pages summarize large explicit selections; following all effect pages reveals their complete affected set.
- Initial M3 datasets have empty quarantine. Prior quarantine history, approval lifecycle and atomic application must be implemented and tested in M4 rather than inferred from previews.
- M4 must enforce this frozen state/output and its additional publication/approval checks; possession of a plan ID never authorizes execution.

## Related Decisions

- [ADR-0002](0002-atomic-state-bound-plans.md): immutable state-bound plans and durable recovery.
- [ADR-0004](0004-expose-six-mcp-tools.md): proposal versus approval/application capabilities.
- [ADR-0011](0011-store-arrow-ipc-snapshots-in-sqlite.md): typed complete snapshots.
- [ADR-0012](0012-version-quality-contract-activation.md): contract activation and revisions.
