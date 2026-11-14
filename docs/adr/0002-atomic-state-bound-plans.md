# ADR-0002: Apply atomic plans against the exact approved state

## Status

Accepted by Kevin Ceciliano Gamboa during project discovery. Storage mechanisms remain undecided.

## Date

2026-11-13

## Context

A repair can remove or alter records used for analysis. Its reviewed impact depends on the current data, contract and normalization mappings. Multiple repair steps can interact: normalization may create duplicates or conflicts. A lost response can also leave the agent uncertain whether a change committed.

## Options Considered

1. **Best-effort, stepwise application.** Retains successful steps after a later failure, but makes the final state diverge from the reviewed whole-plan outcome.
2. **Atomic, state-bound application with a durable receipt.** Produces a clear commit boundary and replay behavior, but requires coordinated persistence of data and execution metadata.
3. **Generic approval reused against current data.** Reduces review friction, but can authorize effects the human never reviewed.

## Decision

We choose an immutable plan bound to exact versions of its data, contract and mappings. Human approval authorizes that plan and state only. Relevant changes invalidate approval and require a newly reviewed proposal.

The preview evaluates the ordered steps and their combined final result. The plan applies completely or publishes no data changes. An operation failure or failed mandatory postcondition rolls back that plan, including its quarantine changes. Independently useful subsets require separately reviewed plans.

Each plan can publish at most one committed version. A durable receipt identifies that publication. Repeating application of an already committed plan returns its original receipt without performing the changes again. This is not a claim of exactly-once network delivery.

After a timeout, the agent queries the plan state. A lost response does not prove that no commit occurred. Crash recovery and concurrent attempts must preserve the publication/receipt invariant.

Preserve data versions and operation history. Restoring prior data is a new approved operation whose preview exposes any later changes it would displace; restoration does not erase history.

Proven defects may be repaired while ambiguous conflicts remain unchanged and explicitly unresolved. Quarantining a conflict group must be included explicitly in the approved plan.

## Consequences

- Persisting the new version, quarantine state, approval consumption and receipt must share a coherent commit boundary; the storage ADR must explain how.
- Tests must cover stale approval, interacting steps, failed postconditions, lost responses, process restart and competing applications.
- A second call for a completed plan returns the receipt even though the dataset has advanced; it must not accidentally apply again or pretend the old approval authorizes a new plan.
- Retaining versions consumes disk space. Capacity limits and retention behavior must be decided before claiming support for a dataset size.
- Atomicity protects execution failures, not a mistaken rule a human approved. Versioned restoration provides a separately reviewed recovery path.

## Related Decisions

- [ADR-0001](0001-structured-repair-boundary.md): permitted repairs and contract authority.
- [ADR-0004](0004-expose-six-mcp-tools.md): plan preparation, inspection and application.
- [ADR-0005](0005-evaluate-server-and-real-agent.md): crash, replay and data-integrity evaluations.

## Record History

Expanded from the initial short decision note on 2026-11-13. Atomic application, state-bound approval, unresolved findings and restoration remain unchanged; later approved replay behavior is now recorded explicitly.
