# Reconciliation fixture matrix

All values are synthetic. No real person, company, invoice, or identifier is used.

| Fixture | Coverage |
|---|---|
| `comparison_left.csv`, `comparison_right.csv` | exact one-to-one, reorder, added, deleted, modified, duplicate left/right, null key |
| `integrity_parent.csv`, `integrity_child.csv` | composite key, missing reference, duplicate parent, null reference |
| `tolerance_left.csv`, `tolerance_right.csv` | amount/date/percentage boundaries, negative/zero values, floating precision |
| `fuzzy_left.csv`, `fuzzy_right.csv` | high/low similarity, tie, region blocking and candidate-limit inputs |
| `weighted_left.csv`, `weighted_right.csv` | transparent multi-field score |
| `review_events.json` | approval, rejection and superseding decision history |
| `formula_injection.csv` | formula-injection sigils in derived exports |

Cancellation, checkpoint recovery, candidate-budget breach, and 10k/100k synthetic exact comparison are generated deterministically in tests and `scripts/benchmark_m2b.py` to avoid committing oversized files.
