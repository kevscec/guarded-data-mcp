# Controlled Data Repair

The project concerns changes to persistent datasets made through an agent-accessible repair workflow.

## Language

**Data repair**:
A deliberate change to a dataset intended to correct a specified defect while preserving data outside that defect.
_Avoid_: Cleanup (when the exact defect and intended correction are unspecified).

**Source dataset**:
The original data provided for analysis, retained as the reference from which a working copy is created.
_Avoid_: Working copy.

**Working copy**:
The persistent dataset on which approved repairs are applied and whose results the analyst can use for analysis.
_Avoid_: Source dataset.

**Repair plan**:
A specific proposed set of changes to a working copy, accompanied by its expected impact.
_Avoid_: Approval.

**Approval**:
A human authorization to apply one exact repair plan; preparing a plan does not authorize its execution.
_Avoid_: Plan, agent confirmation.

**Dataset contract**:
The versioned, human-approved rules defining record identity, permitted values and other quality requirements for a dataset.
_Avoid_: Inferred schema (which alone does not establish the applicable rules).

**Exact duplicate**:
An additional occurrence of a record with the same key and identical values, where the dataset contract requires that key to be unique.
_Avoid_: Similar record, conflicting record.

**Normalization**:
A change of representation using explicit, approved equivalences, without inventing a missing or unknown value.
_Avoid_: Inference, imputation.

**Quarantine**:
The separation of records from the active analytical dataset while preserving their content and the reason for separation.
_Avoid_: Permanent deletion, successful correction.

**Unresolved conflict**:
Records that violate a declared identity rule but lack sufficient evidence for selecting the correct values or record. A successful repair of other defects does not resolve this conflict.
_Avoid_: Repaired duplicate.

**Restoration**:
A newly authorized operation that makes a prior data version current while preserving the history of intervening operations.
_Avoid_: History deletion.
