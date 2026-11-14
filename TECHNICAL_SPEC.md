# Technical specification — controlled data repair MCP

Status: M1–M2 implemented under ADRs 0001–0012: import/inspection, full-scan closed rules, bounded typed queries and human contract/mapping activation. Q26–Q28 accepted the rule/type families and input envelope. Repair schemas, approval execution and real-agent evaluation remain future work.

## Approved architecture

- Python domain core, official MCP SDK over stdio, human CLI and isolated project environment.
- One authoritative SQLite database; PyArrow for CSV and Parquet interchange.
- One table per registered dataset; original preserved; six tools as defined in [ADR-0004](docs/adr/0004-expose-six-mcp-tools.md).
- Human-controlled contracts/mappings and exact plan approval; no agent-side approval capability.
- Atomic, state-bound application with durable replay receipts and versioned restoration.
- Both deterministic and real-agent evaluations are release deliverables.

## Verified foundation runtime

The initial local environment is installed and locked: CPython 3.13.14, `mcp==2.3.0` and `pyarrow==26.0.1`. The local Python build reports SQLite 3.53.1. `.python-version`, `pyproject.toml` and `uv.lock` define the reproducible baseline; CI must verify Windows x64 and Linux x64 separately. Record actual runtime/SQLite versions in future diagnostics and evaluation reports rather than assuming every distribution embeds the same SQLite library.

The MCP package/tag and current documentation disagree about their minimum Python (3.10 versus 3.11); 3.13 satisfies both. Do not combine v1 FastMCP examples with v2 MCPServer APIs. Verify actual current and legacy client negotiation before declaring support.

## Accepted logical data scope and codec requirements

- Support scalar text, boolean, signed int64, exact decimal, date, timestamp and finite float64; preserve naive timestamps as naive. No automatic type inference becomes an approved contract. Decimal128 is the candidate exact-decimal representation to validate in the codec spike.
- Preserve float64 representation and keep it distinct from exact decimals. Reject NaN, infinities and unsupported nested/binary/custom types initially; do not silently convert them to another logical type.
- Contract declares names/order, types, nullability, optional unique business key and versioned quality rules/mappings. Unknown columns and conversion failures are reported; they are not silently dropped.
- Internal row identity identifies a source occurrence independently of a business key. It remains stable through normalization and quarantine, allowing duplicate keys in uncorrected input.
- Null is distinct from empty text. Preserve text IDs such as `001`. Decimal conversion cannot use binary floating point. Date/time conversion cannot silently round, truncate precision or assign a timezone.
- Preserve original source bytes and a SHA-256 manifest. CSV import requires a documented dialect and null policy; CSV export includes a companion schema/null-policy manifest. Parquet round trips preserve the declared supported schema.

## Implemented rules and queries

Initial rule families: required/non-null, unique key, explicit allowed-value set, inclusive typed bounds and ordered comparison of two compatible date/time columns. A rule has a stable ID and human-readable explanation; there is no arbitrary expression, executable plugin or regex engine.

Normalization maps are finite, typed, human-approved source-to-target pairs. Values map once, simultaneously, without recursive chaining. A many-to-one mapping can create duplicates/conflicts, so the full ordered plan must be simulated. Never normalize a business-key column implicitly.

`query_records` selects allowlisted columns and a bounded conjunction of typed `eq`, `ne`, `in`, `lt`, `lte`, `gt`, `gte`, `is_null` and `is_not_null` predicates, or a finding reference. Null predicates are explicit; comparisons do not treat null as empty. Cursors bind to dataset version and filter identity; stable order uses internal row identity. No expression fragments enter SQL.

M2 evaluates all approved rules over the full selected version or returns an error. Required rules and non-null columns flag nulls. Allowed-value, numeric bounds and ordered temporal rules skip nulls; require an explicit required rule to flag those. Ordered rules enforce `column <= other_column` with identical temporal type/unit/zone. Key groups are either wholly identical (exact duplicate finding includes all group members) or conflicting; missing keys are separate. Without a declared key, repeated records are legitimate multiplicity.

Rules have unique IDs and explanations. Contract schema v2 adds rules and finite maps while schema v1 retains its existing canonical hashes. Findings summarize one rule/kind with full occurrence counts and up to ten row IDs, explicitly marking truncation. Finding IDs bind the current revision, contract and selected version/snapshot; they authorize no mutation.

Queries allow at most 20 predicates, 100 literals per predicate and 100 distinct projected columns. All returned/literal non-null scalars use canonical strings with declared dtype: fixed-scale decimals, signed decimal int64, lowercase booleans, ISO dates, hexadecimal `float.hex()` and signed timestamp epoch ticks in the contract's declared unit/zone. This avoids JavaScript integer rounding and Python datetime nanosecond truncation. Equality preserves representation, including float signed zero; inequalities use typed numeric/temporal/text order. See the [M2 walkthrough](docs/m2-walkthrough.md).

Pages return at most 100 rows and 256 KiB of compact UTF-8 structured payload; SDK text mirroring and protocol framing are additional transport bytes. Pagination can stop below the requested row limit to meet the byte ceiling. A single over-budget row requires a narrower projection. Matched counts are complete; returned row evidence can be truncated. Cursors are HMAC-bound to the entire query, page limit, version, snapshot, contract and head revision. They are session-local and expire on restart. Analysis deadlines are cooperative, checked during scans and before returning; a timeout never returns partial analysis as success.

Quarantine names the rule/finding and exact affected occurrence IDs; approved broadening cannot be inferred from a matching sample. Deduplication requires a complete non-null key and full typed equality of the rows; choose a stable survivor and record removed occurrence IDs. A missing key is a separate finding, never permission to collapse unrelated rows.

## Accepted complete versions and proposed persistence details

Complete versions are encoded as Arrow IPC active/quarantine blobs inside SQLite, as recorded in [ADR-0011](docs/adr/0011-store-arrow-ipc-snapshots-in-sqlite.md). M1 registers source bytes, canonical contract and initial typed version atomically. Later repair publication follows the proposed lifecycle below; it is not implemented by the import slice.

Use a dataset head revision that advances on data publication or activated contract/mapping changes. Plans bind this revision, their base data version, contract version, mapping versions and exact proposed effects. Returning to an old content value does not revive an old approval.

M2 appends activations transactionally, with an expected-revision precondition and exact reviewed contract hash. Initial import and activation preflight analysis/result bounds. Physical schema changes require a future explicit migration capability and are refused here. SQLite schema v2 migrates v1 only inside a human write transaction; MCP reads never migrate. Each data version retains its physical import contract. Inspection of any version applies the currently active quality contract and returns both hashes; historical-rule replay is not implemented. Data publication/head advancement on repair enters in M4. See [ADR-0012](docs/adr/0012-version-quality-contract-activation.md).

Store immutable plans and separate approval/execution records. Human review presents the exact plan hash, scope, counts, examples and unresolved findings. CLI confirmation records approval only after revalidating the reviewed revision. Allow explicit revocation before application. No human interaction occurs inside a database write transaction.

Suggested publication sequence:

1. Obtain a bounded write transaction.
2. Return an existing successful receipt for this plan, if present.
3. Revalidate approval, plan integrity and all bound revisions inside the transaction.
4. Publish the new version and quarantine state after required effect/postcondition checks.
5. Consume approval, insert a unique successful receipt and advance the head in that same transaction.
6. Commit; then return the receipt. Roll back on a pre-commit failure.

Failed attempts may have audit entries but cannot masquerade as successful receipts. A process interruption before commit leaves the old publication visible; after commit the result is discoverable through `get_plan`. Competing plans for one revision cannot both publish.

Restoration selects a previous active/quarantine state, previews displaced later changes and publishes a new version under the currently activated contract. It does not secretly restore obsolete rules or erase intermediate history.

## Accepted input envelope and proposed auxiliary limits

The 64 MiB source and combined row/column/cell ceilings are accepted. Other limits below are proposed auxiliary defaults to validate. None is a throughput claim:

| Resource | Ceiling / proposed auxiliary default |
| --- | --- |
| Source file | 64 MiB |
| Rows / columns / cells | 100,000 / 100 / 1,000,000; all limits apply |
| Decoded logical table size | 128 MiB, checked during bounded ingestion |
| Single text value | 64 KiB UTF-8 |
| Page of record evidence | 100 rows and 256 KiB serialized result; paginate below either ceiling |
| Repair steps | 20 per plan |
| Inspection/preview | 30-second execution deadline; no successful result on incomplete plan analysis |
| SQLite lock wait | 5 seconds, then explicit busy response |
| Managed retained content | 2 GiB logical-content quota; refuse writes that exceed it; measure SQLite/journal overhead separately |

Human configuration can lower these limits. Increasing them is an explicit configuration change requiring a benchmark before claiming support. A measured logical-size ceiling is not a claim of an OS-enforced memory sandbox; measure process usage and isolate work as needed during implementation.

Keep complete published history initially; no automatic pruning. Refuse capacity-exceeding imports/plans before publication rather than deleting history silently. Space reclamation needs a later explicitly designed human operation.

## MCP result and failure contract

Every domain response includes dataset/plan identity where applicable, version, completeness, bounded evidence and typed status. Distinguish profile completeness from sample truncation and successful execution from unresolved quality issues.

Proposed domain error codes include unknown dataset/plan, invalid input, unsupported type, missing/revoked approval, stale revision, postcondition failure, resource limit, storage busy and integrity failure. Exact envelopes must be verified against the selected SDK so tool failure flags and structured payloads agree. Never label a domain refusal as successful prose.

The server opens no network port. Logs go to stderr and exclude raw record contents by default. Plan preparation changes metadata even though it does not publish data. Tool annotations describe behavior and are not enforcement.

## Evaluation specification to finalize

- Deterministic fixtures and full-state oracles enter from the first runnable slice. Network data and model credentials are not CI prerequisites.
- Check entire affected/unaffected row sets, multiplicity, quarantine reasons, head revisions, approval consumption and receipts.
- Inject failures before/after publication and use two real processes for CLI/server concurrency and restart tests.
- Preserve prompt-injection content in selected cells; it must not become server instructions or grant capabilities.
- Before measured model runs, freeze task set, repetitions, model/provider, approval-controller policy, outcome oracles and success thresholds. A test-side approval controller must live outside agent-visible tools and approve only fixture-authorized plans.
- Publish model run failures, traces and separate rates for task completion, abstention, inappropriate proposals, unauthorized effects and collateral changes. Passing a finite suite is bounded evidence.

## Remaining decisions

M1–M2 settle IPC encoding, scalar codecs, rule/query semantics, contract activation and pinned SDK auto/legacy stdio compatibility. See the [import walkthrough](docs/m1-walkthrough.md) for exact CSV/type policies and native-decoder limitations. Next specify combined repair simulation and immutable plan persistence, then approval/publication. Choose the real-agent adapter and its measured-suite configuration before evaluating it. Repository identity is `kevscec/guarded-data-mcp`, MIT code license, author Kevin Ceciliano Gamboa using GitHub noreply. Configure identity locally for this repository only.

## References

- [Accepted ADR index](docs/adr/README.md).
- [Development plan](DEVELOPMENT_PLAN.md).
- [MCP release v2.3.0](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.3.0).
- [PyArrow 26.0.1](https://pypi.org/project/pyarrow/26.0.1/).
- [SQLite transaction behavior](https://www.sqlite.org/lang_transaction.html).
- [Python sqlite3 date/time adapter caveats](https://docs.python.org/3/library/sqlite3.html#default-adapters-and-converters-deprecated).
