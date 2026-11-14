# Working on Guarded Data MCP

Read [README.md](README.md), the [ADR index](docs/adr/README.md), the [technical specification](TECHNICAL_SPEC.md) and the current milestone in [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) before changing architecture. Accepted decisions describe intended behavior; they do not establish that a feature has been implemented or evaluated.

## Boundaries

- Keep domain semantics independent of the MCP SDK. CLI and MCP call the same services with different exposed capabilities.
- M3 plans freeze their contract, ordered steps, exact manifest and typed previews. Preserve the final non-regression/conservation checks; individual intermediate steps may create defects only when later steps resolve them. Preparation writes proposals, never published data. MCP preparation refuses old workspace formats instead of migrating them.
- Preserve schema-v1 plan canonical serialization when extending the protocol; introduce a versioned format rather than silently rehashing existing proposals. Approval/execution state belongs in separate records.
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
uv run python -m pytest -q
uv run python -m evals.runner
```

M1–M2 include functional tests and a deterministic evaluation runner that starts the real stdio subprocess in automatic and legacy modes, including human CLI activation while the server remains alive. Run checks appropriate to changed behavior, including failure-path/full-state oracles. Preserve historical reports when extending the runner. Do not substitute coverage percentages, import checks or scripted tool calls for real-agent evaluation; the separate real-agent suite remains an M7 deliverable.

## Public evidence and data

- No employer material or credentials in code, documentation, fixtures or commit history.
- Runtime datasets, credentials, local logs and unreviewed model traces remain outside Git. Keep redistributable synthetic fixtures explicitly separated from acquired source data.
- Source data retains its source terms; the repository's MIT license does not relicense external datasets.
- Commits use the author's configured personal identity in this repository. Do not change global Git identity.
- README and reports must distinguish planned, implemented and measured behavior. Include observed failures and limitations.
