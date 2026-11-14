# M2: investigate quality under an approved contract

First [import the synthetic example and configure stdio](m1-walkthrough.md). The examples use dataset ID `example`; use a fresh workspace or inspect its current revision before activation. The three MCP tools are read-only. Repair planning/application is not implemented yet.

## Inspect the initial contract

Call `inspect_dataset` with `{"dataset_id":"example"}`. The complete scan finds an `exact_duplicate` group containing occurrences 1 and 2 under the declared unique key. It does not classify `unfamiliar` as corrupt: the initial contract has no category rule. Missing keys and conflicting keys have distinct findings. Identical records without a declared unique key are not labeled duplicates.

`analysis_complete` describes the full scan. Each finding's `row_count` covers all matching occurrences; `sample_row_ids` contains at most ten and `evidence_truncated` indicates omitted evidence. `no_violations` means no violations of the active rules, not universal data correctness. Listing datasets does not evaluate rules.

## Review and activate rules/maps through the human CLI

Review [the schema-v2 example](../evals/cases/m1/quality-contract.json). It explicitly declares allowed categories and a finite synthetic equivalence. Obtain its canonical hash, then copy that hash into activation:

```sh
uv run guarded-data contract-check evals/cases/m1/quality-contract.json
uv run guarded-data --workspace workspace activate-contract example --contract evals/cases/m1/quality-contract.json --approve-contract REVIEWED_SHA256 --expected-revision 1
uv run guarded-data --workspace workspace inspect example
```

Activation advances the head revision to 2 and changes no source bytes, data version, row values or quarantine. The map is approved metadata for future plan simulation; it is not executed. The new category rule now flags occurrence 4. Wrong hashes, stale expected revisions, changed physical schemas and resource-over-budget contracts are refused. A valid hash is not a secret or independent proof of human identity; the CLI is the human-authority channel in this project's MCP-only trust boundary.

Each data version keeps its original physical contract. Inspection returns that hash separately from the current active quality contract, including when a historical data version is requested. See [ADR-0012](adr/0012-version-quality-contract-activation.md).

## Query typed records

Call `query_records` with:

```json
{
  "dataset_id": "example",
  "columns": ["id", "amount", "note"],
  "predicates": [
    {"column": "amount", "op": "gte", "values": ["1.00"]},
    {"column": "id", "op": "ne", "values": ["001"]}
  ],
  "limit": 20
}
```

This returns occurrence 4, preserving `id` as text and `amount` as `{"dtype":"decimal128","value":"1.00"}`. Each record has a stable `row_id` and a dictionary of typed `cells`. Null has `value: null`; empty text has `value: ""`. All non-null values use canonical strings:

| Type | Literal / wire form |
| --- | --- |
| text | Exact text, including leading zeroes |
| boolean | `true` or `false` |
| int64 | Signed decimal string, no leading zeros or plus sign |
| decimal128 | Fixed scale from contract, e.g. `12.30` |
| float64 | Python `float.hex()`, e.g. `-0x0.0p+0` |
| date | ISO `YYYY-MM-DD` |
| timestamp | Signed epoch ticks in the active contract's unit and timezone; no datetime conversion |

Equality compares typed representations, including signed zero. Order predicates use typed order. Null only matches explicit `is_null`/`is_not_null`; `ne` does not include nulls. Predicates form a conjunction. `eq`, `ne`, `lt`, `lte`, `gt`, `gte` take one literal; `in` takes 1–100; null predicates take none. At most 20 predicates are accepted. Unknown fields/operators and expression fragments are refused.

To investigate a finding, use its current `finding_id` in `query_records`; this selects the full affected occurrence set rather than only the ten sample IDs. Optional predicates can narrow it. Finding references expire when their reviewed state changes.

## Follow bounded evidence

Use `limit: 2` to obtain a page, then call again with exactly the same arguments plus `cursor` set to `next_cursor`. Records are ordered by stable occurrence ID. Follow the cursor until it is null. `matched_count` counts the full selection; `evidence_truncated` says whether further evidence remains after this page.

Pages stop at 100 records or 256 KiB of compact UTF-8 structured payload, whichever comes first. MCP text mirroring/framing adds transport bytes. Narrow the projection when one record alone exceeds the budget. Full scans use a cooperative 30-second deadline; incomplete analysis produces an error, never a successful partial-quality claim.

Cursors bind the dataset/version, snapshot, contract, head revision and complete query including page size. A changed query or revision returns `STALE_CURSOR`; alteration or server restart returns `INVALID_CURSOR`. Restart pagination after either refusal. Reactivating identical contract content still advances the revision and invalidates earlier evidence.

## Reproduce evidence

```sh
uv run python -m pytest -q
uv run python -m evals.runner
uv run python -m evals.runner --mode legacy
```

The [M2 report](evals/m2-results.json) records deterministic protocol checks, human activation from a separate process while the server is alive, and a full-state oracle for source bytes, every row, multiplicity and empty quarantine. Functional tests additionally cover conflicts, missing keys, allowed values, required fields, exact bounds, ordered dates, scalar precision, output budgets, migration and rollback failures. These are scripted evaluations; real-agent evaluation remains M7.
