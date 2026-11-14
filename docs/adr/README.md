# Architecture Decision Records

These records capture the decisions accepted during discovery for the controlled data repair MCP project. They explain choices and trade-offs; they do not claim the software is implemented or replace a development specification.

## Index

| ADR | Decision | Status | Date |
| --- | --- | --- | --- |
| [0001](0001-structured-repair-boundary.md) | Restrict execution to structured repairs under approved contracts | Accepted | 2026-11-13 |
| [0002](0002-atomic-state-bound-plans.md) | Apply atomic plans against the exact approved state | Accepted | 2026-11-13 |
| [0003](0003-use-registered-local-datasets.md) | Operate on registered local single-table datasets | Accepted | 2026-11-13 |
| [0004](0004-expose-six-mcp-tools.md) | Expose six tools for investigation and controlled execution | Accepted | 2026-11-13 |
| [0005](0005-evaluate-server-and-real-agent.md) | Evaluate server guarantees and real-agent outcomes | Accepted | 2026-11-13 |
| [0006](0006-pin-public-demo-and-synthetic-defects.md) | Pin a NYC 311 sample and label synthetic defects | Accepted; source terms must be documented before distribution | 2026-11-13 |
| [0007](0007-use-python-and-mcp-stdio.md) | Use Python and the official MCP SDK over stdio | Accepted | 2026-11-13 |
| [0008](0008-use-sqlite-and-pyarrow.md) | Keep authoritative state in SQLite and use PyArrow for interchange | Accepted | 2026-11-13 |
| [0009](0009-use-closed-rules-and-explicit-scalar-types.md) | Use closed quality rules and explicit scalar types | Accepted | 2026-11-13 |
| [0010](0010-retain-complete-versions-with-bounds.md) | Retain complete versions within an explicit initial envelope | Accepted | 2026-11-13 |

Decision-maker: Kevin Ceciliano Gamboa. Acceptance comes from explicit answers in the discovery conversation; it is not evidence of completed implementation or independent engineering review.

## Conventions

- Preserve `docs/adr/` and the existing four-digit numbering.
- Use the accompanying [template](template.md). Include context, real alternatives, rationale and concrete positive/negative consequences.
- Keep each record focused on a significant decision; keep the full design and development plan separate.
- New, unapproved decisions start as Proposed. Accepted, Deprecated, Superseded and Rejected describe the decision lifecycle, not test results.
- Preserve old decisions when superseding them and link both directions. Reference governing ADRs at relevant code entry points when implementation exists.

## What remains undecided

- Exact runtime/SDK pins and supported protocol/client matrix; Python and stdio are accepted in ADR-0007.
- Physical encoding and exact CLI/server commit mechanism; SQLite/PyArrow and complete versions are accepted in ADR-0008/0010.
- Precise codecs, filter vocabulary and composition semantics; scalar types and closed quality-rule families are accepted in ADR-0009.
- Auxiliary operational limits, pagination and machine-readable error taxonomy; initial input ceilings and no automatic pruning are accepted in ADR-0010.
- Detailed human approval issuance/revocation and stale-plan lifecycle.
- Real-agent provider/model, case set, repetitions, acceptance thresholds and credential configuration.
- First-public-commit setup and attribution verification. The user selected `kevscec/guarded-data-mcp`, MIT and GitHub noreply authorship.

These need explicit technical specification or validation before the affected milestone. No unlisted dependency version, codec representation or auxiliary limit is accepted by implication. Review the [technical specification](../../TECHNICAL_SPEC.md) and [development plan](../../DEVELOPMENT_PLAN.md) for accepted input limits, remaining details and deliverable gates.

## Source guidance

The user selected [Spencer Pauly's architecture-decision-records skill](https://github.com/spencerpauly/awesome-cursor-skills/blob/main/resources/architecture-decision-records/SKILL.md) as the governing ADR style. It favors concise records with context, alternatives, decision and consequences, with the full design kept outside ADRs. Earlier Vercel and wshobson references were reviewed but are not additional approval workflows for these records.
