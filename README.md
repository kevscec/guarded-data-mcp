# Guarded Data MCP

An MCP server project for controlled local data repair: an agent investigates a dataset and proposes changes, while a human approves an exact plan and the server enforces its permitted effects.

**Status: M3 immutable repair proposals implemented.** Import and investigate typed CSV/Parquet data, then simulate ordered normalization, exact deduplication and explicit quarantine through five MCP tools. Proposals freeze the contract, exact effects and typed previews without changing published data. Contract/mapping activation is human-only. Approval/application and real-agent evaluations remain later milestones.

## The problem

Giving an agent a general SQL or Python executor makes its effective permissions much broader than a data-cleaning request. Two similar rows are not necessarily duplicates, a missing value does not establish its replacement, and a successful tool call does not establish that the data is correct.

This project chooses a bounded repair surface and explicit human authority. Its initial repair families are exact deduplication under an approved unique-key rule, normalization through approved mappings and quarantine with preserved content and reasons.

## Accepted design

- Local Python server using the official MCP SDK over stdio; human CLI for import, contract activation, plan approval and export.
- Registered, single-table CSV/Parquet datasets; preserve the original and repair a versioned working copy.
- SQLite owns data, quarantine, approvals and durable receipts; PyArrow handles interchange.
- Approval binds the exact plan and reviewed data/contract versions. Application is atomic and replay returns the original receipt.
- Structured operations rather than arbitrary SQL/Python; unresolved conflicts remain explicit.
- Deterministic protocol evaluations and a separate real-agent suite, with full-state outcome checks and published failures.

The stated trust boundary is an agent limited to the exposed MCP tools. It does not establish protection against an agent with unrestricted access to the host operating system.

## Tool surface and implementation status

| Tool | Responsibility | Status |
| --- | --- | --- |
| `list_datasets` | Discover registered datasets with bounded pagination. | Implemented |
| `inspect_dataset` | Inspect contracts, provenance, full profiles and approved quality rules. | Implemented |
| `query_records` | Investigate bounded typed records with structured filters or a finding reference. | Implemented |
| `prepare_plan` | Simulate and persist exact repair instructions, effects and previews. | Implemented; restoration planned M5 |
| `get_plan` | Review immutable proposal/effects and stale state. | Implemented; approval/execution state planned M4 |
| `apply_plan` | Apply the approved plan without changing its instructions. | Planned M4 |

There is no agent-side import, contract activation or approval tool. The server registers four read tools and one proposal-writing tool; none can apply data changes. Inspection distinguishes complete analysis from truncated evidence and reports `no_violations` only with respect to activated rules. Unfamiliar categories are not defects without an approved applicable rule. Dataset listing does not run quality analysis.

## Try the first slice

```sh
uv sync --locked
uv run python -m evals.runner
```

This self-contained evaluation imports synthetic data through the human CLI, starts the actual stdio server, checks output schemas and expected refusals, and compares the entire persisted dataset against an independent expected result. It preserves duplicates, leading-zero IDs, exact decimals and null versus empty text. It uses no model or network data.

Follow the [import walkthrough](docs/m1-walkthrough.md) to connect a client, the [M2 walkthrough](docs/m2-walkthrough.md) to investigate quality and the [M3 walkthrough](docs/m3-walkthrough.md) to prepare/review proposals. Existing workspaces require human `workspace-upgrade` before preparation.

The [M3 results](docs/evals/m3-results.json) record 27 deterministic cases per protocol mode: automatic (`2026-07-28`) and legacy (`2025-11-25`), using the pinned SDK. They include restart recovery, full predicted-output oracles and unchanged published-state checks. The [M2 report](docs/evals/m2-results.json) remains historical evidence for commit `5fd5809`, including its observed concurrency failure and correction; the [M1 report](docs/evals/m1-results.json) covers commit `8f54883`. These results do not certify other clients or an agent's decisions.

## Development

Python 3.13 and [uv](https://docs.astral.sh/uv/) are required. Use the project-owned environment:

```sh
uv sync --locked
uv run python scripts/check_docs.py
uv run ruff check .
uv run ruff format --check .
uv run python -m pytest -q
uv run python -m evals.runner --mode legacy
```

CI runs documentation/lint/format checks and behavioral tests on Windows and Ubuntu. The protocol tests run the evaluation harness with the pinned SDK's automatic and legacy negotiation modes. They are deterministic protocol evaluations, not real-agent runs. Desktop host products are not yet individually certified.

## Decisions and delivery

- [Architecture decision index](docs/adr/README.md): accepted choices, alternatives and consequences.
- [Technical specification](TECHNICAL_SPEC.md): scope, invariants and remaining implementation details.
- [Development plan](DEVELOPMENT_PLAN.md): deliverables, dependencies and acceptance gates.
- [Glossary](GLOSSARY.md): domain terminology.
- [Discovery context](DISCOVERY.md): how the accepted scope emerged.

The public demonstration will use a pinned, minimized NYC 311 sample and clearly labeled synthetic defect variants. NYC data is not yet distributed; M1 fixtures are project-authored synthetic records. Source terms and provenance must accompany any future external data; the code license does not relicense that data.

## License

[MIT](LICENSE) for the code and project-authored documentation. External datasets retain their source terms and attribution.
