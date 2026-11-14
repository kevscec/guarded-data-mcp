# ADR-0009: Use closed quality rules and explicit scalar types

## Status

Accepted by Kevin Ceciliano Gamboa in response to Q26 and Q27.

## Date

2026-11-13

## Context

The repair surface needs precise semantics that can be checked independently of the model. Free-form expressions expand execution authority, while inferred types can turn identifiers into numbers or change the meaning of nulls and timestamps.

## Options Considered

1. **Infer types and accept general expressions/plugins.** Flexible, but hides semantic changes and adds executable behavior beyond the documented repair families.
2. **Treat every value as text.** Simple to preserve initially, but loses typed bounds, date comparisons and faithful Parquet interchange.
3. **Declare scalar types and a closed rule vocabulary.** Produces checkable behavior, with explicit refusals for unsupported types and rules.

## Decision

We choose explicit text, signed integers, booleans, exact decimals, dates, timestamps and finite `float64` values. Distinguish floats from exact decimals and preserve their representation. Reject NaN, infinities and nested types initially rather than coercing them silently. The physical codecs and supported precision require tests before claiming compatibility.

The initial quality rule families are required fields, unique keys, explicit allowed values, typed numeric bounds and comparison between compatible date fields. Normalization uses human-approved explicit equivalences. There are no free expressions, regex rules or executable plugins.

The contract determines meaning: inference may help draft it but does not approve it. Preserve text identifiers and null versus empty text. Do not invent missing values, assign a timezone silently or accept lossy decimal/date conversions.

## Consequences

- New rule families and unsupported data types require an explicit extension, not a prompt workaround.
- Codecs need behavioral round-trip tests, including finite floats, signed zero, exact decimals, null/empty and timezone semantics.
- Findings depend on the activated contract; unfamiliar categories are not automatically corruption.
- Closed filters must remain typed and non-executable even when implemented using internal SQL.

## Related Decisions

- [ADR-0001](0001-structured-repair-boundary.md): structured repair authority.
- [ADR-0008](0008-use-sqlite-and-pyarrow.md): storage/interchange codecs.
- [ADR-0010](0010-retain-complete-versions-with-bounds.md): bounded first implementation.
