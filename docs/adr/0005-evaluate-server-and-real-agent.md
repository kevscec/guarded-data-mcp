# ADR-0005: Evaluate both server guarantees and real-agent outcomes

## Status

Accepted by Kevin Ceciliano Gamboa during project discovery.

## Date

2026-11-13

## Context

A working tool does not establish that an agent will investigate correctly, respect uncertainty or choose the right repair. Conversely, one successful agent demonstration does not establish that the server rejects unsafe requests. The project is public engineering evidence, so evaluation is a required deliverable rather than optional coverage work.

## Options Considered

1. **Unit tests only.** Reproducible and cheap, but misses protocol behavior and end-to-end agent decisions.
2. **Agent demonstrations only.** Shows a usable workflow, but can hide server defects and selected successful runs.
3. **Deterministic and real-agent evaluation layers.** Separates enforcement from model behavior, at the cost of maintaining fixtures, traces and model-dependent runs.

## Decision

We choose both layers. CI runs deterministic tests and evaluations through the actual MCP protocol without requiring an external model or live public dataset API. Cases include correct repairs and expected refusals, intermediate failures, concurrency and recovery.

A real-agent suite exercises end-to-end tasks and checks resulting data, not just tool-call success. Publish failures as well as successes. Any observed unauthorized data mutation or collateral data damage blocks the first release until corrected and re-evaluated.

Include a deterministic workflow reference for tasks whose decisions are already completely specified. The evaluation must not assume that adding a model improves repair correctness. Its useful contribution is investigation, interpretation of the user's goal, selection of permitted changes and honest explanation of limits.

## Consequences

- Fixtures need expected complete outputs, preserved unaffected records, quarantine contents and reasons, and expected unresolved findings.
- Required failure families include absent/stale approval, altered state, key ambiguity, combined-step interactions, failed postconditions, replay, lost responses and restart.
- Prompt-injection cases must treat cell instructions as data and assess both agent behavior and server enforcement. A refusal by the server and an appropriate decision by the agent are separate results.
- Model runs require separate credentials and incur variable cost; they are not silently replaced by scripted tool calls.
- Before measuring the agent suite, specify its tasks, repetitions, success criteria, model configuration and approval simulation. Preserve traces and report all attempted measured cases.
- Passing a finite suite does not prove universal safety. The README must state the tested scope and observed limitations.

## Related Decisions

- [ADR-0001](0001-structured-repair-boundary.md): repair semantics.
- [ADR-0002](0002-atomic-state-bound-plans.md): failure and recovery invariants.
- [ADR-0004](0004-expose-six-mcp-tools.md): protocol surface under evaluation.
- [ADR-0006](0006-pin-public-demo-and-synthetic-defects.md): fixture provenance and injected defects.
