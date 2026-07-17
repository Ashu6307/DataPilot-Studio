# Performance Budgets and Measurement

Budgets are guardrails, not claims. Measurements must record date, exact source shape/format, sampled/full behavior, duration per stage, peak process memory, output size, and hardware.

| Scenario | Guardrail intent |
|---|---|
| 10k rows | Full discovery/preview remains interactive and bounded |
| 100k rows | Practical local processing with visible progress and stable memory |
| 500k CSV rows | Batched processing or graceful warning/refusal before instability |
| Wide data | Warn when cell-count and sample-memory estimates exceed policy |
| High-cardinality text | Bound profiling samples and distinct-value retention |
| Excel export | Respect 1,048,576-row sheet limit and split/refuse explicitly |

Default limits are configurable: preview rows 200, profile sample rows 10,000, maximum discovered cells warning 5,000,000, and memory-risk ratio 0.25 of available memory. CSV batching is supported where operations permit. Excel ingestion remains read-only but is not claimed as true streaming.

## Local measurement context

- Test date: 2026-07-17
- Machine: Dell Vostro 15 3510
- CPU: Intel Core i5-1135G7, 4 cores / 8 logical processors
- RAM: 23.7 GiB
- OS: Windows (local development environment)
- Python: 3.14.0; Node: 24.14.0

Measured results are appended only after benchmark execution.

## Measurements — 2026-07-17

Synthetic data used eight columns with high-cardinality names and leading-zero record IDs. Wide data used 1,000 rows × 250 columns. Times are wall-clock seconds. Python peak is `tracemalloc` and excludes some native Polars allocations.

| Dataset | Batched read | Batched trim | Discovery | Preview 200 | Python peak during discovery |
|---|---:|---:|---:|---:|---:|
| 10,000 × 8 CSV (714,547 B) | 0.2856 | 0.1753 | 1.3077 | 0.0395 | 14,357,484 B |
| 100,000 × 8 CSV (7,244,857 B) | 2.2547 | 1.7563 | 8.8373 | 0.0995 | 127,907,835 B |
| 500,000 × 8 CSV (36,668,457 B) | 9.7700 | 10.0717 | 44.9658 | 0.0784 | 636,235,718 B |
| 1,000 × 250 wide CSV (1,013,455 B) | 0.3990 | 0.4238 | 2.7433 | 0.6125 | 16,427,915 B |

Observed implication: bounded preview stays sub-second because it no longer loads the complete CSV. Full discovery still materialises source rows and reached roughly 636 MB of traced Python allocations at 500k × 8; use the warning policy and batched execution for larger sources. These measurements do not claim native-memory completeness or hardware portability.

Excel export was measured separately using the same eight-column synthetic schema and the production evidence-pack exporter:

| Rows × columns | Export time | Python peak | Output size |
|---|---:|---:|---:|
| 10,000 × 8 | 9.7128 s | 7,911,261 B | 392,265 B |
| 100,000 × 8 | 86.5193 s | 78,810,224 B | 3,914,351 B |

The 500,000-row Excel export was not executed in this pass: extrapolated wall time is operationally expensive and full discovery already demonstrated material memory growth. CSV batching at 500k is measured above; Excel export at that size remains a documented validation limitation rather than an invented result. Excel’s hard row limit is 1,048,576 rows per sheet, and exports must split or refuse above it.
