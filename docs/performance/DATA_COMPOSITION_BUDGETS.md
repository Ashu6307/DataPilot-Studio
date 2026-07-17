# Data Composition Budgets

Budgets are guardrails, not cross-machine promises.

| Scenario | Guardrail |
|---|---|
| Catalog preview | 100 files / 1M estimated rows should remain bounded and cancellable |
| Append | 100k aligned rows operation target under 2 s after input read |
| Exact join | 100k × 100k one-to-one target under 10 s; many-to-many blocks by default |
| Pivot | 100k input rows / 100 generated columns target under 5 s; >250 columns warn/block by default |
| Split | 100k rows / 20 CSV files target under 20 s with full reconciliation |
| Memory | Preview estimates risk; native allocations are not represented by `tracemalloc` |

## Measurement — 2026-07-17

Hardware: Dell Vostro 15 3510, Intel Core i5-1135G7 (4 cores/8 logical),
approximately 23.7 GiB usable RAM, Windows 11 Pro, Python 3.14.0, Polars 1.42.1.

| Scenario | Wall time | Python traced peak | Output |
|---|---:|---:|---:|
| Append 10 pre-read CSV tables, 100k rows | 0.0375 s | 25,844 B | 100,000 rows |
| Left exact join 100k × 100k | 4.6946 s | 44,007,935 B | 100,000 rows |
| Pivot 100k rows to 100 value columns | 0.0416 s | 5,740 B | 1,000 rows × 101 columns |
| Split 100k rows to 20 CSV files | 11.5085 s | 33,977,666 B | 100,000 reconciled rows |

Append timing excludes CSV reads because it measures the composition operation;
split includes CSV serialization. Polars native allocations are not fully captured
by Python `tracemalloc`. Reproduce with `python scripts/benchmark_m2a.py`.
