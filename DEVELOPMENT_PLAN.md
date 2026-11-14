# Development plan — controlled data repair MCP

Status: development sequence based on accepted ADRs 0001–0010. Q26–Q28 accepted the initial types/rules, full-version approach and input ceilings. Repository identity is accepted: `kevscec/guarded-data-mcp`, MIT, author Kevin Ceciliano Gamboa with GitHub noreply email. Auxiliary defaults in [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) remain explicit technical-validation work.

Progress: M0 foundation is published. M1 import/inspection and its deterministic evaluation are implemented with local behavioral/protocol evidence. CI runs that suite on Windows and Ubuntu on every push. M2–M8 are not started. The public repository is [kevscec/guarded-data-mcp](https://github.com/kevscec/guarded-data-mcp).

The sequence uses deliverables and dependencies, not a calendar. Every functional milestone includes its own evaluation cases; the harness is not deferred to the end. The map below describes target responsibilities. M1 keeps these in focused modules (`domain.py`, `storage.py`, `codec.py`, `ingest.py`, `services.py`, `server.py`, `__main__.py`) rather than creating empty subpackages for future work.

## Repository map

```text
src/guarded_data_mcp/
  domain/       # logical contracts, records, rules, plans, findings
  storage/      # SQLite connections, migrations, versions, approvals, receipts
  codecs/       # explicit logical/physical conversions
  services/     # inspection, preview, application, restoration
  adapters/     # CSV/Parquet boundaries
  cli/          # human-only import, contract, review, approval, export
  mcp/          # six SDK handlers and schemas
evals/
  cases/        # pinned inputs, contracts, fault scenarios and expected outputs
  runner/       # deterministic protocol runner and independent approval controller
  agent/        # real-model adapter and trace/reporting
tests/
  unit/
  integration/
  protocol/
examples/nyc311/
docs/adr/
.github/workflows/
```

The domain never imports MCP handlers. CLI and MCP adapters call the same services. Only storage owns persistence/transactions; only the human CLI exposes approval/contract activation. No source, credential or runtime dataset enters Git implicitly.

## M0 — Establish public ownership and a reproducible baseline

Dependencies: repository identity confirmed. Create the public repository before the first commit and set the chosen author identity only in its local Git configuration.

Deliver: public repository under the user's account before the first commit; ADRs and honest planned-status README; `.gitignore`; project configuration; project-owned Python environment; exact locked dependencies; Windows/Linux CI setup.

Acceptance:

- [x] Public visibility is verified before committing; GitHub attributes the first commit to kevscec using the selected noreply identity.
- [x] Existing documentation is checked for employer materials and credentials before staging.
- [x] The isolated environment is recreated from its lock locally and by Windows/Linux CI without changing the host's existing environment.
- [x] Published SDK/PyArrow packages import successfully; actual Python/SQLite/PyArrow versions are recorded. Actual stdio/client compatibility remains an M1 protocol gate, not a foundation claim.
- [x] CI runs meaningful documentation, lint, formatting and runtime-import checks; no fabricated passing product tests or completed-feature claims.

## M1 — First vertical slice: import, inspect and reproduce

Dependencies: M0. Initial type/limit choices are approved. Resolve the storage/codec spike before migrations are treated as stable.

Deliver: explicit contract parser, source preservation, initial SQLite version, human import CLI, `list_datasets` and `inspect_dataset` over a real stdio subprocess. Create the deterministic evaluation runner and first full-state oracle here.

Acceptance:

- [x] A tiny fixture is imported and inspected through actual MCP requests; the contract and version match the CLI view.
- [x] Original bytes/hash and row multiplicity survive; text IDs and null/empty distinctions match the declared supported schema.
- [x] Unknown datasets, incompatible types and exceeded input limits produce explicit failures with no registered partial dataset.
- [x] Actual stdio sessions pass using automatic and legacy negotiation. CI runs the same slice without network/model access. Publication is complete only after verifying the pushed revision's remote CI result.

## M2 — Investigate quality with bounded evidence

Dependencies: M1 and confirmed closed rule/filter vocabulary.

Deliver: full-scan rule evaluation, deterministic findings, `query_records`, version-bound pagination and human contract/mapping activation.

Acceptance:

- [ ] Detect exact duplicates separately from conflicting keys and legitimate multiplicity.
- [ ] New/missing categories are not called corrupt without an approved applicable rule.
- [ ] Queries preserve types and stable row identities; changed versions or altered filters cannot reuse a cursor silently.
- [ ] Hostile identifiers, expression fragments and unbounded requests cannot become executable code or arbitrary file access.
- [ ] Truncated row evidence and incomplete analysis remain explicit; neither becomes a whole-dataset quality claim.

## M3 — Materialize exact, immutable repair proposals

Dependencies: M2.

Deliver: pure repair simulation for the three accepted families, combined-step checks, persisted `prepare_plan` output, exact affected-row manifest and `get_plan` review state. No data-application capability is enabled yet.

Acceptance:

- [ ] Preview expected output matches a full-state oracle; active data remains unchanged.
- [ ] Normalization-induced duplicates/conflicts are included in the combined outcome.
- [ ] Missing-key records are not deduplicated together; conflicting values are not resolved by guessing.
- [ ] Quarantine preserves every selected occurrence and reason; samples cannot silently broaden the affected set.
- [ ] Timeout/incomplete analysis does not produce a reviewable successful plan.

## M4 — Human approval and atomic application

Dependencies: M3 and a documented approval issuance/revocation and commit-state model.

Deliver: CLI review/approval/revocation, `apply_plan`, transactionally coordinated publication/approval consumption/receipt and explicit domain refusals.

Acceptance:

- [ ] Missing, fabricated, revoked, altered-plan and stale-state approval cannot publish data.
- [ ] Human review is outside the write transaction; confirmation rechecks the exact reviewed revision.
- [ ] Failure in any repair stage or mandatory postcondition publishes no data or quarantine change.
- [ ] Two concurrent applications cannot publish twice; competing plans cannot overwrite a newer revision.
- [ ] Lost responses and process termination before/after commit are reconciled using the persisted plan/receipt.
- [ ] Applying a completed plan returns its original receipt without rerunning effects.

## M5 — Restore and deliver usable results

Dependencies: M4.

Deliver: approved restoration through the existing plan tools, full history inspection, CSV/Parquet export and provenance/quality package.

Acceptance:

- [ ] Restoration creates a new version, preserves intermediate history and previews displaced later changes.
- [ ] Restoration cannot silently reactivate obsolete contracts/mappings.
- [ ] Export uses one immutable selected version; a failed export does not change working data or leave a package presented as complete.
- [ ] Supported type/schema round trips pass; CSV limitations and null policy accompany its output.
- [ ] Reports preserve unresolved findings and quarantine provenance instead of claiming unconditional cleanliness.
- [ ] Capacity limits refuse writes without silently pruning source or history.

## M6 — Public NYC 311 demonstration and reproducible adversarial cases

Dependencies: M3 for controlled variants, M5 for the full walkthrough; source-term documentation before distributing rows.

Deliver: minimized source snapshot with acquisition/terms manifest, separately labeled corrupted variants, approved example contract and a complete local walkthrough.

Acceptance:

- [ ] The walkthrough runs offline after acquisition and verifies pinned hashes.
- [ ] Each injected defect has an auditable expected effect; none is attributed to the original city data.
- [ ] Public source terms/attribution are separate from the code license; addresses/coordinates are outside the selected projection.
- [ ] Demo includes successful repair, an unresolved conflict, refused unauthorized/stale application and approved restoration.

## M7 — Real-agent evaluation with honest comparative evidence

Dependencies: M4 for the basic suite, M5–M6 for complete release evidence; selected provider/model and fixture-side approval policy.

Deliver: real-model adapter, frozen evaluation configuration, independent approval controller, traces, full-state graders and deterministic workflow reference.

Acceptance:

- [ ] Fix cases, repetitions, thresholds and model configuration before the measured run; keep pilot runs distinguishable.
- [ ] An actual model calls the actual MCP transport. Scripted calls cannot be reported as real-agent evaluation.
- [ ] Approval-controller capabilities are not exposed to the agent; approval policy is fixture-defined rather than "approve whatever was proposed".
- [ ] Publish every attempted measured case, including failures, abstentions and prompt-injection attempts.
- [ ] Grade intended outcomes, unauthorized effects, collateral changes and reporting separately; compare fully specified tasks with the deterministic reference.
- [ ] Observed unauthorized mutation or collateral damage blocks release until fixed and rerun.

## M8 — Release evidence and portfolio delivery

Dependencies: required checks in M0–M7 pass, unresolved acceptance decisions are closed and client compatibility is documented from real tests.

Deliver: decision-focused README, installation/client configuration, threat boundary, exact supported types/limits, test/eval commands, results and limitations, tagged release and an evidence-backed CV bullet.

Acceptance:

- [ ] A reviewer can identify the six tools, human-only authority, important refusals and evaluation results within five minutes.
- [ ] Fresh-clone walkthrough and CI pass on the declared platforms.
- [ ] Commands reproduce deterministic evidence without secrets or live upstream dependencies; model runs document their separate prerequisites.
- [ ] Public code, fixtures, examples and commit history contain no employer material or credentials and use the user's identity.
- [ ] README distinguishes tested guarantees from unsupported environments and universal-safety claims.

## Immediate next gate

Execute M1 as the first complete vertical slice. Resolve the documented codec/schema details through targeted validation before implementing persistence. No dates or elapsed-time targets define completion.
