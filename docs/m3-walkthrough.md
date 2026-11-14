# M3: prepare and review an immutable repair proposal

M3 adds `prepare_plan` and `get_plan`. The server exposes five tools; `apply_plan` and human approval are not implemented. A proposal's ID, successful simulation or passing postconditions never authorizes application.

## Prepare the workspace and contract

Follow the [import walkthrough](m1-walkthrough.md) and [M2 contract activation](m2-walkthrough.md), using dataset ID `example`. That example is at head revision 2 after activation. New imports already use workspace schema v3. For a workspace created before M3, the human runs:

```sh
uv run guarded-data --workspace workspace workspace-upgrade
```

The migration is transactional and preserves source/version contents. MCP inspection continues to read old formats; MCP preparation returns `WORKSPACE_UPGRADE_REQUIRED` without migrating them. `prepare_plan` writes proposal metadata and preview blobs, so its read-only hint is false. It changes no working records, published version, active quarantine or head revision.

## Simulate an ordered plan

Call `prepare_plan` with the current revision from inspection:

```json
{
  "dataset_id": "example",
  "expected_revision": 2,
  "request": {
    "steps": [
      {"kind": "normalize", "mapping_id": "example-equivalence"},
      {"kind": "deduplicate"}
    ]
  }
}
```

The synthetic mapping changes occurrence 4 from `unfamiliar` to `open`; deduplication removes occurrence 2 while retaining occurrence 1. The predicted active IDs are 1, 3 and 4, with no quarantine. The original four-row dataset stays unchanged. Nulls, literal `\N`, empty text, exact decimal scale and stable occurrence identities remain preserved.

Steps run in the supplied order. A normalization step maps each non-null source value once through its approved map; pairs do not recursively chain within that step. Separate explicit steps can map again. A mapping of a business-key column additionally requires `allow_key_change: true`. Maps cannot fill nulls or invent unapproved values.

Deduplication requires an approved unique key, keeps the smallest occurrence ID in each wholly identical complete-key group and never resolves conflicting groups or merges missing keys. A complete plan with no effects returns `NO_EFFECT`; individual no-op steps are allowed when the whole plan has effects.

## Quarantine exact occurrences

As an alternative to the normalization above, prepare a separate proposal:

```json
{
  "dataset_id": "example",
  "expected_revision": 2,
  "request": {
    "steps": [
      {"kind": "deduplicate"},
      {
        "kind": "quarantine",
        "rule_id": "categories",
        "finding_kind": "allowed_values",
        "row_ids": [4]
      }
    ]
  }
}
```

The predicted active IDs are 1 and 3. The quarantine preview retains occurrence 4's full typed record and the exact approved rule's explanation. An effect records the rule, kind and simulation finding ID. Every requested ID must still violate that rule at that ordered step. Empty/repeated/unknown IDs or selecting a valid record are refused. Explicitly selecting two IDs from a 30-row finding quarantines only those two; omitted rows remain unresolved.

Initial M3 data has empty quarantine. Previously published quarantine and its historical reasons enter with M4 application; M3 does not claim that lifecycle is implemented.

## Combined checks and failure behavior

Each proposal freezes the full contract/maps, exact base version and head revision, snapshot/quarantine hashes, ordered request, effect manifest and both typed preview blobs. Mandatory checks preserve types and conserve every occurrence among the predicted active set, quarantine and deduplication removals.

The final result cannot introduce new rule violations: for each `(rule ID, kind)`, its final violating occurrence IDs must be a subset of the original IDs. Existing unresolved findings remain explicit. Intermediate violations are allowed if subsequent steps resolve them. For example, normalization that creates duplicates needs a later deduplication step. Normalization that creates a conflicting key cannot use deduplication to guess a winner; it needs an explicit valid quarantine selection or returns `POSTCONDITION_FAILED`.

Simulation, step, deadline, storage/quota or postcondition failure persists no partial proposal. The save transaction rechecks all bound state. A contract activation during simulation returns `STALE_REVISION` instead of saving a proposal against outdated rules.

## Review all effects and recover after restart

Call `get_plan` using the returned `plan_id`:

```json
{"plan_id": "RETURNED_PLAN_ID", "limit": 50, "after_effect": 0}
```

Follow `next_after_effect` on the same immutable plan until null. Pages contain at most 100 effects and 256 KiB compact UTF-8 structured payload. SDK text mirroring/framing adds transport bytes. Step summaries give selected counts; every exact selected occurrence is in the complete paginated effect manifest. Normalization effects contain typed before/after values, deduplication effects identify the survivor, and quarantine effects preserve the reason. Original unchanged/deduplicated values remain accessible in the bound base version.

`findings_before` describes the input's approved rules. `predicted_findings` describes simulation only; simulation finding IDs are not references for querying published records. Neither counts nor previews claim that application occurred. M3 returns `approval_status: not_supported`, `execution_status: not_enabled` and `can_apply: false`.

The human can read the complete frozen contract, request and manifest through:

```sh
uv run guarded-data --workspace workspace review-plan RETURNED_PLAN_ID
```

The canonical document's SHA-256 defines the plan ID; creation time is separate. Identical requests against the same current state return the same ID without duplicating storage. `get_plan` works after server restart and after contract changes; changed state marks the proposal `stale` while preserving its original content. Resume effect pagination by ID and effect position after restart. Repeating preparation with an obsolete expected revision is refused.

## Bounds and evidence

Plans allow 1–20 closed steps, at most 100,000 effect entries and a 16 MiB canonical document. Existing data ceilings, 30-second cooperative preview deadline and 2 GiB logical retained-content quota also apply. All persisted proposal documents and previews count against quota; no automatic pruning occurs. These limits do not guarantee every possible plan over the maximum input size will fit. Native Arrow work is not a process-level CPU/memory sandbox.

```sh
uv run python -m pytest -q
uv run python -m evals.runner
uv run python -m evals.runner --mode legacy
```

The [M3 report](evals/m3-results.json) records 27 deterministic cases per protocol mode, including full independent comparisons of predicted active/quarantine records and unchanged published state. Behavioral tests cover combined defects, explicit scopes, failures, rollback, migration, quota, concurrent preparation, typed precision and restart. These are scripted protocol evaluations; actual model behavior remains M7 work. See [ADR-0013](adr/0013-persist-exact-simulated-proposals.md) for the persistence/postcondition trade-off.
