# Guarded Data MCP

An MCP server project for controlled local data repair: an agent investigates a dataset and proposes changes, while a human approves an exact plan and the server enforces its permitted effects.

**Status: foundation and accepted design. Repair tools are under development.** The repository currently contains the architecture decisions, technical specification, development plan, isolated dependency baseline and documentation checks. No completed repair workflow or evaluation results are claimed yet.

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

## Planned tool surface

| Tool | Responsibility |
| --- | --- |
| `list_datasets` | Discover registered datasets. |
| `inspect_dataset` | Inspect contracts, versions, profiles and findings. |
| `query_records` | Investigate bounded records with structured filters. |
| `prepare_plan` | Simulate and persist an exact repair/restoration proposal. |
| `get_plan` | Inspect approval, execution and persisted outcome. |
| `apply_plan` | Apply the approved plan without changing its instructions. |

There is no agent-side approval tool. Tool names above describe the accepted design, not endpoints already available in this foundation commit.

## Development

Python 3.13 and [uv](https://docs.astral.sh/uv/) are required. Use the project-owned environment:

```sh
uv sync --locked
uv run python scripts/check_docs.py
uv run ruff check .
uv run ruff format --check .
```

CI runs these foundation checks and verifies runtime imports on Windows and Linux. Functional tests and the deterministic evaluation runner enter with the first runnable import/inspection slice; a successful foundation check is not a passing product evaluation.

## Decisions and delivery

- [Architecture decision index](docs/adr/README.md): accepted choices, alternatives and consequences.
- [Technical specification](TECHNICAL_SPEC.md): scope, invariants and remaining implementation details.
- [Development plan](DEVELOPMENT_PLAN.md): deliverables, dependencies and acceptance gates.
- [Glossary](GLOSSARY.md): domain terminology.
- [Discovery context](DISCOVERY.md): how the accepted scope emerged.

The public demonstration will use a pinned, minimized NYC 311 sample and clearly labeled synthetic defect variants. It is not downloaded or distributed by this foundation. Source terms and provenance must accompany any future external data; the code license does not relicense that data.

## License

[MIT](LICENSE) for the code and project-authored documentation. External datasets retain their source terms and attribution.
