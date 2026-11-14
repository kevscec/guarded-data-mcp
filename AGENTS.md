# Working on Guarded Data MCP

Read [README.md](README.md), the [ADR index](docs/adr/README.md), the [technical specification](TECHNICAL_SPEC.md) and the current milestone in [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) before changing architecture. Accepted decisions describe intended behavior; they do not establish that a feature has been implemented or evaluated.

## Boundaries

- Keep domain semantics independent of the MCP SDK. CLI and MCP call the same services with different exposed capabilities.
- SQLite owns authoritative state and transaction publication. PyArrow handles CSV/Parquet interchange.
- The agent has no approval or contract-activation tool. Plans are immutable and approvals bind the reviewed state.
- Preserve original records, multiplicity, logical types, quarantine reasons and operation history. Never silently coerce unsupported values or report a bounded sample as full validation.
- Use the closed rule/operation vocabulary. Do not introduce executable expressions, arbitrary SQL/Python tools, regex rules or plugin execution as shortcuts.
- Add a new focused ADR when replacing an accepted architectural decision; preserve and cross-link the old record.

## Environment and checks

Use the project-owned uv environment and locked dependencies. Do not install into or reconfigure unrelated Python environments.

```sh
uv sync --locked
uv run python scripts/check_docs.py
uv run ruff check .
uv run ruff format --check .
```

Functional tests and the deterministic evaluation runner start in M1. Once present, run the checks appropriate to the changed behavior, including actual stdio/protocol checks and failure-path oracles. Do not substitute coverage percentages, import checks or scripted tool calls for real-agent evaluation.

## Public evidence and data

- No employer material or credentials in code, documentation, fixtures or commit history.
- Runtime datasets, credentials, local logs and unreviewed model traces remain outside Git. Keep redistributable synthetic fixtures explicitly separated from acquired source data.
- Source data retains its source terms; the repository's MIT license does not relicense external datasets.
- Commits use the author's configured personal identity in this repository. Do not change global Git identity.
- README and reports must distinguish planned, implemented and measured behavior. Include observed failures and limitations.
