# Candidate directions — historical exploration

Candidate A was subsequently selected. B and C remain unselected alternatives. Current accepted decisions are indexed in [docs/adr/README.md](docs/adr/README.md); this file preserves the earlier hypotheses and research.

## A. Controlled data repair

User: someone maintaining a local analytical dataset.
Problem: detect and fix duplicates, invalid values, or broken references without silently damaging valid records.
Demonstration: inspect a real public dataset, diagnose an issue, preview an explicit repair, obtain independent human authorization, apply only to the reviewed version, and verify invariants. Controlled corruptions may be added for reproducible evaluation, clearly distinguished from the original public data.
Consequential operation: deleting or modifying persistent records.
Evaluation opportunities: incorrect repair; ambiguous duplicate; stale data; forged/replayed approval; partial failure; repeat execution; preservation of unaffected rows.
Main risk: becoming a generic SQL wrapper or an unlimited data-cleaning platform. Select one coherent family of repairs first.

## B. Controlled incident recovery

User: a developer operating a small local service stack.
Problem: diagnose an outage and execute an allowed recovery action without granting an agent an arbitrary shell.
Demonstration: inject a known fault into an actual runnable service stack, inspect observations, propose a bounded action, authorize it independently, execute and verify recovery or report failure.
Consequential operation: restarting a service or changing its operational configuration.
Evaluation opportunities: wrong target; misleading log content; changed state since diagnosis; repeated action; action succeeds but health does not recover; timeout with unknown outcome.
Main risk: building a deployment/observability platform instead of a focused recovery workflow. Docker access itself is privileged and needs an explicit boundary.

## C. Evidence-controlled career documents

User: someone tailoring a CV from an evidence-graded career knowledge base.
Problem: preserve attribution, evidence strength and redlines while an agent selects and transforms claims.
Demonstration: expose structured evidence, propose changes, validate a document, and prevent unsupported or unauthorized updates to approved records.
Consequential operation: changing approved claims/evidence or replacing an approved output. Whether this naturally satisfies the brief's dangerous-operation requirement remains open; do not add deletion merely to check a box.
Evaluation opportunities: missing source; unsupported upgrade in attribution; contradictory evidence; private redline; instructions embedded in a job posting.
Main risk: deterministic source tracing does not establish that arbitrary prose is semantically supported. That must be bounded or evaluated honestly.

## Public sources inspected

- https://github.com/kevscec/grounded-cv
- https://github.com/kevscec/grounded-cv/blob/main/scripts/verify.py
- https://github.com/kevscec/vencord-server-cleanup
- https://github.com/kevscec/WoW-SmartDeals
- https://github.com/kevscec/quick-cita-cr
- https://github.com/github/github-mcp-server
- https://github.com/modelcontextprotocol/servers
- https://duckdb.org/docs/stable/operations_manual/securing_duckdb/overview
- https://duckdb.org/docs/stable/sql/statements/transactions
- https://docs.docker.com/engine/security/

## Cross-cutting design question

A human approval boundary cannot be demonstrated merely by letting the same agent set an approval flag. If approval is selected as a control, its issuer and the exact authorized state/action must be defined explicitly. Existing projects supply inspiration, not proof that a copied mechanism is appropriate for an MCP threat model.

## Demo dataset research (subsequently selected)

NYC 311 service requests: https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9

Initial official metadata research identifies a text unique_key, date fields and daily updates. This is a candidate for a minimized public snapshot, not a claim that its actual records contain repairable errors. Demo data access, reproducible snapshot acquisition, and redistribution terms must be verified before accepting it. Any deliberately introduced corruption must be labeled and kept distinguishable from the source data.
