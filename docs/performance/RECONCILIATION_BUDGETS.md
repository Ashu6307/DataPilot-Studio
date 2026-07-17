# Reconciliation Budgets

Budgets are configurable safety controls, not arbitrary scale claims.

| Budget | Default |
|---|---:|
| Candidate pairs | 1,000,000 |
| Duplicate group | 10,000 |
| Review items | 50,000 |
| Fuzzy fields | 5 |
| Minimum fuzzy threshold | 0.70 |
| Export sheets | 30 |
| Rows per sheet | 1,000,000 |
| Execution-time warning | 1,800 seconds |
| Evidence snapshot fields | 20 |

Exact key comparison uses indexed tuples and is not a Cartesian operation.
Tolerance stages without constraints are bounded before materializing pairs.
Fuzzy stages always require blocking and stop when candidate count exceeds the
configured limit. Large duplicate groups and review queues have independent
limits. Excel limits are validated before publication.

Measurement is reproducible with:

```powershell
python scripts/benchmark_m2b.py
```

The benchmark reports wall time, Python-traced peak allocation, candidate counts,
input characteristics, and outputs. Native Polars allocations are not included by
`tracemalloc`; results therefore must not be treated as complete process RSS.

## Measurement — 2026-07-17

Hardware: Dell Vostro 15 3510, Intel Core i5-1135G7 (4 cores/8 logical),
approximately 23.7 GiB usable RAM, Windows 11 Pro, Python 3.14.0, Polars 1.42.1.

| Scenario | Inputs | Candidates | Wall time | Python traced peak | Output |
|---|---:|---:|---:|---:|---|
| Exact comparison | 10k x 10k | 10,000 indexed pairs | 0.9700 s | 34.04 MiB | 10,000 unchanged |
| Exact comparison | 100k x 100k | 100,000 indexed pairs | 10.2548 s | 342.35 MiB | 100,000 unchanged |
| Blocked fuzzy/review | 2k x 4k | 4,000 | 0.7529 s | 17.63 MiB | 2,000 reviews |
| Blocked amount tolerance | 10k x 10k | 10,000 | 2.2137 s | 52.91 MiB | 10,000 matches |
| Duplicate-key groups | 10k x 10k | 0 comparisons | 0.6519 s | 41.61 MiB | 1 ambiguous group |
| Excel/CSV/JSON/ZIP export | 2,000 reviews | 4,000 source candidates | 2.9036 s | 24.85 MiB | 9.52 MiB artifacts |

Exact timings include construction of comparison records after pre-read frames;
they do not include file discovery. The fuzzy benchmark deliberately creates two
blocked candidates per left row and is a review-queue/export stress case, not an
unrestricted fuzzy scalability claim.
