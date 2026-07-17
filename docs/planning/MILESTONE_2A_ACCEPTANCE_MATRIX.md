# Milestone 2A Acceptance Matrix

| # | Acceptance criterion | Evidence | Status |
|---:|---|---|---|
| 1 | Select structurally different Excel/CSV files | batch catalog API, Composition Studio multi-upload, `test_composition_vertical_slice.py` | Pass |
| 2 | Discover each file without fixed ranges | `multi_source.py`, discovery suite | Pass |
| 3 | Review/repair schema alignment | versioned alignment matrix and UI | Pass |
| 4 | Append canonical inputs | composition unit and vertical-slice tests | Pass |
| 5 | Configure generic multi-key joins | `JoinConfiguration`, join tests | Pass |
| 6 | Cardinality warnings and approval | one/one, one/many, many/one, many/many tests | Pass |
| 7 | Dynamic grouped summaries | all nine aggregate functions tested | Pass |
| 8 | Pivot and unpivot | reshape and width-limit tests | Pass |
| 9 | Split on selected canonical fields | multi-field, condition, row-limit tests | Pass |
| 10 | Safe collision-resistant names | traversal, invalid character, collision, sheet-limit tests | Pass |
| 11 | Full operations use background jobs | composition executor/API and checkpoint endpoints | Pass |
| 12 | Sources remain unchanged | vertical-slice pre/post fingerprint assertions | Pass |
| 13 | Accepted/rejected/output rows reconcile | append, split, manifest assertions | Pass |
| 14 | Audit/lineage includes source and plan version | output package and runtime tests | Pass |
| 15 | M1A/M1B workflows stay compatible | migration and complete regression suites | Pass |
| 16 | Required quality gates pass | final command record in delivery handoff | Pass |

The protected tags `v0.1.0-m1a` and `v0.2.0-m1b` are unchanged.
