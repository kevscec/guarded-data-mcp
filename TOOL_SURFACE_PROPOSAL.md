# MCP surface and evaluation proposal

Status: historical surface proposal. The six tool names/responsibilities, replay guarantees, release-evidence direction and NYC 311 demo were accepted during discovery; later rounds selected the stack, closed rule/type scope and initial input limits. Current accepted decisions are recorded in [docs/adr/README.md](docs/adr/README.md). Consult [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) for implementation status and remaining schema/codec/evaluation details.

## Agent-facing tools

| Tool | Input intent | Structured result | Reason for a separate tool |
| --- | --- | --- | --- |
| list_datasets | Bounded cursor pagination | Registered dataset IDs, current versions, brief quality summary | Discover authorized scope without arbitrary paths |
| inspect_dataset | Dataset ID and optional explicit version | Approved contract and mappings, schema, full-scan findings or explicit incomplete status, provenance, bounded version history | Establish applicable rules and evidence before proposing changes |
| query_records | Dataset/version, allowlisted columns and typed filters or finding ID, bounded cursor pagination | Matching rows and stable record references, version, next cursor and completeness metadata | Investigate findings without SQL, file access or unbounded output |
| prepare_plan | Dataset/version, contract version, typed repair steps OR restoration target | Persisted immutable proposal ID, state dependencies, exact affected record manifest, before/after counts, bounded examples, remaining findings and mandatory postconditions | Simulate and materialize the exact proposal a person can review |
| get_plan | Plan ID | Proposal details, approval state, execution state and durable receipt if applied | Review authorization requirements and reconcile uncertain outcomes |
| apply_plan | Plan ID only | Committed version, durable receipt, verification and remaining findings, or actionable typed refusal | One controlled mutation entry point; agent cannot supply authorization or alter the reviewed plan |

Tools never approve plans. Preparing a persisted plan changes metadata, even though it does not change working data. Annotations must reflect that distinction.

Contract changes can be proposed by the agent as structured content for human review. Importing or activating a contract remains a human CLI action; it is not hidden inside a repair plan.

The exact filter operators, rule vocabulary, data-type semantics and resource limits remain to be specified. No free-form expression language may enter through filters, rules or mappings.

## Human CLI responsibilities

- Import CSV/Parquet, preserve source bytes, register a single-table working dataset and review an explicit contract.
- Review and activate versioned contracts and normalization mappings.
- Review an immutable plan with its impact, unresolved findings and exact dependencies; approve that plan outside MCP.
- Export a selected committed version as CSV/Parquet with provenance and quality report.
- Inspect complete history and full manifests without depending on model context limits.

## Proposed replay and failure behavior

- A plan can publish at most one committed data version.
- Repeating apply_plan for a previously committed plan returns its original receipt and does not reapply the changes.
- After a timeout, the agent consults get_plan; a lost response is not evidence that no commit occurred.
- A crash before publication leaves the current working version unchanged; a crash after publication preserves a discoverable receipt.
- Concurrent attempts must not both publish. Durable uniqueness and atomic version preconditions enforce this, not the prompt.
- Domain refusals are MCP tool failures with machine-readable codes and actionable next steps. Protocol errors remain distinct.
- Incomplete inspection and truncated evidence are labeled explicitly. Samples do not establish whole-dataset quality or whole-plan safety.

## Proposed evaluation matrix

| Family | Cases and oracle |
| --- | --- |
| Correct repair | Exact deduplication under approved identity rule; approved normalization; quarantine preserves every removed record and reason; compare full expected output |
| Ambiguity | Conflicting key values remain unchanged unless explicitly approved for quarantine; legitimate repeated records under a non-unique contract remain intact |
| Composition | Normalization creates duplicates or conflicts; preview evaluates ordered steps and verifies their combined final result |
| Least privilege | Unknown dataset, path/SQL/expression injection, arbitrary code, invalid columns or oversized requests are refused |
| Approval | Absent, fabricated, stale, altered-plan or consumed authorization cannot publish a new version |
| Atomicity | Failures in each repair stage and required postcondition leave working data and quarantine logically unchanged |
| Replay and concurrency | Lost response, duplicate call, process restart and competing plans cannot cause duplicate publication or silent overwrites |
| Recovery | Restore prior data as a new approved version; show displaced subsequent changes and preserve history |
| Honest reporting | Unresolved findings remain visible; limit, timeout or partial inspection cannot be reported as complete validation |
| Prompt injection | Instructions embedded in cell values remain data; evaluate both server enforcement and agent behavior |
| Data fidelity | Null vs empty string, text keys, timezone-free dates, row multiplicity and round-trip format behavior must match the approved contract |

Deterministic tests and protocol-level evaluations run in CI without external model credentials or a live public API. Fixtures are pinned and include expected refusals.

A separate real-agent suite runs end-to-end tasks through the actual MCP transport with controlled human-approval events. Persist model/version, prompts, tool traces, dataset/contract versions and full-state outcome checks. Report task success, inappropriate proposals, unauthorized mutations, collateral changes, honest abstentions and call/cost information separately. Finite passing cases do not prove universal safety.

Proposed release rule: deterministic required cases pass; any observed unauthorized mutation or collateral data damage in the real-agent suite blocks release. Publish all attempted agent cases and repetitions, including failures. Choose the task set and task-success acceptance criterion before the measured run. Include a deterministic workflow reference for tasks whose choices are already fully specified; do not assume using a model improves repair correctness.

## Proposed public demonstration

NYC 311 is a viable candidate: a public GET returning five projected records was verified with HTTP 200 and no credentials. A more selective ordered query timed out; network fetching is an acquisition step, not a demo or CI prerequisite.

Use a stored, minimized snapshot of unique_key, created_date, closed_date, agency, complaint_type, borough and status. Preserve source bytes and acquisition manifest/hash. Keys are text; sample dates lack a timezone offset. Missing fields and novel categories are not automatically defects.

Keep the source sample distinguishable from intentionally corrupted evaluation variants. Label injected duplicates, conflicts and normalization cases. Do not claim these are errors found in the city's original records. Terms and attribution must be resolved before redistribution; do not assume the data inherits the code license.

## Official references checked

- https://py.sdk.modelcontextprotocol.io/servers/structured-output/
- https://py.sdk.modelcontextprotocol.io/servers/handling-errors/
- https://py.sdk.modelcontextprotocol.io/servers/tools/
- https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio
- https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- https://modelcontextprotocol.io/specification/2026-07-28/server/resources
- https://data.cityofnewyork.us/api/views/erm2-nwe9.json
- https://data.cityofnewyork.us/resource/erm2-nwe9.json?$select=unique_key,created_date,closed_date,agency,complaint_type,borough,status&$limit=5
- https://cityofnewyork.github.io/opendatatsm/publicpolicies.html
