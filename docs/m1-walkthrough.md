# M1: import and inspect a local dataset

M1 implements human-only CSV/Parquet import and the `list_datasets` / `inspect_dataset` MCP tools. It does not repair data or evaluate quality rules yet. The examples below use project-authored synthetic records, not NYC data.

## Install and evaluate

```sh
uv sync --locked
uv run python -m pytest -q
uv run python -m evals.runner
uv run python -m evals.runner --mode legacy
```

The standalone evaluation imports a fixed fixture using the human CLI, starts a real stdio subprocess and validates output schemas, registered scope, profile and expected refusals. An independent SQLite/Arrow reader compares the entire result against the expected records, multiplicity and source bytes before and after protocol calls. The suite is deterministic and does not use a model or credentials.

## Review and import the synthetic example

Review the [contract](../evals/cases/m1/contract.json) and [source](../evals/cases/m1/source.csv). Obtain the digest of the canonical contract:

```sh
uv run guarded-data contract-check evals/cases/m1/contract.json
```

Copy the returned `contract_sha256` into the human import command:

```sh
uv run guarded-data --workspace workspace import example evals/cases/m1/source.csv --format csv --contract evals/cases/m1/contract.json --approve-contract REVIEWED_SHA256
uv run guarded-data --workspace workspace list
uv run guarded-data --workspace workspace inspect example
```

`REVIEWED_SHA256` is replaced with the digest from the review. The digest binds the exact reviewed contract; it is not a secret or a standalone proof of human identity. Authority comes from the human-only CLI channel in the declared trust boundary. No import or approval capability is registered with MCP.

Re-importing an existing dataset ID is refused and leaves the original version intact. The workspace is local, gitignored and contains source bytes and managed versions. A successful import preserves duplicate business keys and nulls for later quality assessment.

## Connect an MCP client

Configure a local stdio server with the absolute path to the project's `.venv` Python executable:

```json
{
  "command": "ABSOLUTE_PATH_TO_PROJECT_PYTHON",
  "args": ["-m", "guarded_data_mcp", "--workspace", "ABSOLUTE_PATH_TO_WORKSPACE", "serve"]
}
```

On Windows the project executable is `.venv/Scripts/python.exe`; on Linux it is `.venv/bin/python`. The JSON above is a command/argument definition to adapt to the host client's configuration format, not a claim that every host shares the same file format.

Call `list_datasets` with `{}` and `inspect_dataset` with `{"dataset_id":"example"}`. Client inputs are registered IDs and optional versions, never source paths. Inspection returns typed contract/provenance, row counts and full null counts, without raw record values or local source paths. `quality_status` is explicitly `not_evaluated` and `findings_evaluated` is false.

Tested protocol combinations are the pinned MCP SDK client against the pinned SDK server using `mode=auto` (negotiated `2026-07-28`) and `mode=legacy` (negotiated `2025-11-25`). Each mode passed nine cases in the [recorded result](evals/m1-results.json). Desktop host products are not yet individually certified.

## Supported input policy

- CSV: UTF-8, comma delimiter, header, standard doubled quotes, multiline quoted fields, lowercase `true`/`false` for booleans. Headers and order match the contract exactly.
- Unquoted `\N` means null. Quoted `"\N"` means literal text. Empty text is preserved; an empty non-text token must be valid for its declared type or is refused.
- Parquet: column names/order and logical Arrow types match exactly, including decimal scale and timestamp unit/timezone. Unsupported nested/dictionary/custom schemas are refused rather than inferred or cast.
- Types: text, boolean, int64, decimal128, finite float64, date32 and timestamp with explicit unit and either no timezone or UTC. NaN/infinity are refused; float signed zero is retained.
- Input limits: 64 MiB source, 100,000 rows, 100 columns and 1,000,000 cells, applied together. CLI can lower source-byte/row limits; it cannot raise them.
- Auxiliary defaults: 128 MiB accumulated logical table size, 64 KiB per text value, 2 GiB logical retained-content quota, 30-second cooperative import deadline and a bounded five-second database lock wait.

Unsupported structure or conversion is an error, not an automatic quarantine decision. Arrow conversion messages can contain raw data; the CLI and tools return sanitized domain errors. Nullability and the declared key are stored but their quality rules enter in M2.

The decoded-data limit is checked per batch after native decoding, and the deadline is cooperative. These are not guarantees against arbitrary memory allocation or a stalled native decoder on a malicious compressed file. Original files are supplied by the trusted human operator; the server's agent-facing tools cannot acquire files or initiate imports.
