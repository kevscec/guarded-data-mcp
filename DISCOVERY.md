# Project discovery

Status: product, base-stack and initial type/limit decisions recorded in docs/adr/; M0 public repository/environment setup is in progress.

## Settled direction

- Primary portfolio audience: AI Engineer / Applied AI roles.
- Personal usefulness is optional; the project must solve a concrete useful problem.
- Existing public projects at https://github.com/kevscec may supply inspiration.
- Scope will be defined by requirements and a development plan, not a calendar or hourly budget.
- The complete demonstration should run locally; deployment is an open decision to revisit if the problem warrants it.
- The earlier brief's weekend limit is superseded. Its 3-6 tool suggestion is provisional, not a selected design.
- Preserve the evidence goals: deliberate tool surface, least privilege, typed outputs, failure handling, and a meaningful evaluation harness.
- No employer materials or credentials. Public repository from the first commit, with the user's own commit identity.

## Selected direction

- Controlled data repair through an MCP server (candidate A).
- Evaluation has two layers: deterministic server behavior and end-to-end tasks performed by a real agent.
- The agent evaluation must assess task outcomes and unintended changes, not just successful tool calls.

## Accepted product boundaries

- Primary user: an analyst preparing local datasets for analysis.
- Preserve the original source and apply repairs to a persistent managed working copy.
- Every data mutation initially requires human authorization of the exact repair plan, through a mechanism separate from agent-controlled MCP tools.
- The permission boundary must be explicit: MCP controls alone do not constrain an agent with unrestricted operating-system access.

## Accepted repair model

- Three initial repair families: exact duplicates under a declared unique key; normalization using approved explicit mappings; quarantine of records violating explicit rules, preserving their content and reason.
- Conflicting records sharing a key are not automatically resolved by guessing a winner.
- Dataset contracts are versioned and human-approved. The agent may propose contract changes but cannot independently approve or weaken the rules used to judge its repairs.
- MCP tools expose structured operations, not arbitrary SQL or Python execution.

## Accepted execution guarantees

- Approval is bound to the exact plan and versions of the working data, contract and normalization mappings; relevant changes invalidate it.
- A repair plan is atomic: operation failures or failed mandatory postconditions roll back all of that plan's data changes.
- Independently reviewable work can be split into separate approved plans.
- Proven defects can be repaired while ambiguous key conflicts remain unchanged and explicitly unresolved; successful execution is not a claim of complete dataset quality.
- Quarantining an unresolved conflict group must itself be explicitly included in an approved plan.
- Preserve versions and history. Restoring a prior data version is a new approved operation, with its impact on subsequent changes made explicit; it does not erase history.

## Accepted product interface

- Reusable engine, with a single table per dataset and multiple independently registered datasets. Cross-table repair and external database synchronization are outside the initial scope.
- Human imports CSV or Parquet by CLI; the agent works only with registered dataset identifiers, without arbitrary local paths.
- Human reviews and approves exact plans by CLI. No approve_plan MCP tool.
- Declared security boundary: an agent limited to MCP capabilities; no claim of protection from unrestricted operating-system access.
- Human exports CSV or Parquet by CLI together with provenance, contract version, repair counts, quarantine reasons, unresolved findings and verification results.

## Current open decisions

- Exact runtime/SDK pins and supported protocol/client matrix.
- Physical versions, codecs and precise concurrency/commit mechanism.
- Logical types, rule/filter schemas, resource limits and detailed approval lifecycle.
- Real-agent evaluation configuration, cases, repetitions and measurable acceptance criteria.
- Whether to extend a public project or create an independent project.
- Verify first-public-commit authorship and CI. Repository name, MIT code license and noreply identity are accepted.

## Accepted tool surface and release evidence

- Six MCP tools: list_datasets, inspect_dataset, query_records, prepare_plan, get_plan and apply_plan.
- A plan publishes at most one version. Repeated application of a committed plan returns the original persistent receipt.
- After an uncertain response, inspect plan state rather than assuming no commit occurred. Cover restarts and concurrent attempts.
- CI runs deterministic and protocol-level evaluations. Run a real-agent suite before the first release and publish failures as well as successes.
- Observed unauthorized mutations or collateral data damage block publication until corrected.
- Include a deterministic workflow reference for fully specified tasks.
- NYC 311 is the principal public example: pin a minimized snapshot, preserve provenance/hash, and distinguish synthetic defects from original source records.
- Document source redistribution terms separately from the code license.

## Decision records

The authoritative accepted decisions are indexed in [docs/adr/README.md](docs/adr/README.md). Acceptance records design agreement, not completed software. Q25 accepted Python, the official MCP SDK over stdio, SQLite as the single authoritative store and PyArrow for CSV/Parquet. The index lists remaining technical choices explicitly.

Reviewable drafts now exist in [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) and [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md). Proposed defaults are labeled and are not accepted by implication.

Q26–Q28 accepted closed rules, finite float64 support, complete versions and the combined initial input ceilings. The user then selected `kevscec/guarded-data-mcp`, MIT for code and Kevin Ceciliano Gamboa's GitHub noreply identity. The public repository was created before any local commit; publication of the foundation is in progress.

## Working method

Use Matt Pocock's grill-me / grill-with-docs and their grilling / domain-modeling dependencies for discovery. For ADRs, the user selected Spencer Pauly's architecture-decision-records skill after considering other references. Keep concise decision records separate from the eventual implementation specification and development plan. This file is discovery context, not an implementation authorization.
