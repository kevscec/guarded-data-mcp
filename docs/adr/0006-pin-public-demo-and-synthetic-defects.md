# ADR-0006: Pin a NYC 311 sample and label synthetic defects

## Status

Accepted by Kevin Ceciliano Gamboa as the principal demonstration direction. Publication of source rows remains subject to documenting the applicable source terms.

## Date

2026-11-13

## Context

The demonstration needs real public data and exact expected repair outcomes. A changing upstream API cannot reproduce a historical evaluation by itself. Public records also do not establish that a suspicious value is incorrect or which conflicting record is true.

A small projected NYC 311 API request returned HTTP 200 without credentials. A more selective ordered request timed out. Acquisition is feasible, but neither upstream availability nor stable results may be assumed.

## Options Considered

1. **Fetch live data for every demo/test.** Fresh, but depends on network availability and mutable upstream state.
2. **Use only fictional data.** Gives exact expected outcomes and easy redistribution, but weakens the real-source demonstration.
3. **Pin a public sample and derive labeled defect variants.** Combines real provenance with controlled oracles, but requires source-term documentation and clear separation of original and modified data.

## Decision

We choose NYC 311 dataset `erm2-nwe9` as the principal public example, with a stored, minimized snapshot and explicit provenance. The demo and CI operate without a live API dependency after acquisition.

Select `unique_key`, `created_date`, `closed_date`, `agency`, `complaint_type`, `borough` and `status`. Preserve source bytes, acquisition time, exact request, selected columns, source attribution and SHA-256. Do not infer that all fields are mandatory from a small sample. Preserve text identifiers and do not silently assign a timezone to local date-time strings.

Create separately identified variants with deliberately introduced duplicates, conflicts and normalizable representations. Record each injected change and expected outcome. Do not describe these variants as evidence of errors in the city's source records. Missing values and unfamiliar categories are not defects unless an applicable approved rule establishes that.

Before distributing source rows, document the applicable source terms, attribution and modifications. Data does not inherit the repository's code license. If redistribution cannot be settled, use a human acquisition command with redistributable synthetic fixtures rather than dropping the evaluation harness.

## Consequences

- A new download is a new source version, not a reproduction of an old snapshot; store and verify the original snapshot hash.
- Import/acquisition needs bounded timeouts and clear upstream failure reporting. Offline tests must not depend on NYC API availability.
- Source data, controlled variants and expected outputs need separate manifests so the evaluation oracle can be audited.
- Omit incident addresses and coordinates from the selected projection; they are unnecessary for the accepted repair demonstrations.
- The engine remains dataset-independent; the example's quality rules belong in its contract.

## Related Decisions

- [ADR-0003](0003-use-registered-local-datasets.md): reusable engine and provenance.
- [ADR-0005](0005-evaluate-server-and-real-agent.md): deterministic fixtures and real-agent evaluation.

## References

- [NYC 311 dataset](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9).
- [Official dataset metadata](https://data.cityofnewyork.us/api/views/erm2-nwe9.json).
- [NYC Open Data public policies](https://cityofnewyork.github.io/opendatatsm/publicpolicies.html).
- [NYC Open Data terms](https://data.cityofnewyork.us/stories/s/Terms-of-Use/k9k7-3cje).
