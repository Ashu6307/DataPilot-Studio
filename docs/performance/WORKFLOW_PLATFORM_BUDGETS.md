# Workflow Platform Budgets

| Configurable control | Default |
|---|---:|
| Nodes per workflow | 250 |
| Edges per workflow | 1,000 |
| Subflow depth | 5 |
| Concurrent ready nodes | 4 |
| Workflow payload | 2,000,000 bytes |
| Parameter payload | 100,000 bytes |
| Stored run history | 1,000 |
| Checkpoint retention | 30 days |

Budgets are validation controls, not scale claims. Results are reproducible with:

```powershell
python -m scripts.benchmark_m3a --output docs/performance/m3a_benchmark_2026-07-17.json
```

## Measurement — 2026-07-17

Hardware reported by the harness: Windows 11 build 26200, Intel Family 6 Model
140 processor, AMD64, 8 logical cores, Python 3.14.0. `tracemalloc` captures
Python allocations but not complete process RSS or native library allocations.

| Scenario | Wall time | Python traced peak |
|---|---:|---:|
| Plan 25-node linear DAG | 0.022803 s | 237.4 KiB |
| Validate 100-node linear DAG | 0.062374 s | 836.8 KiB |
| Plan branching DAG | 0.004187 s | 35.7 KiB |
| Expand 20-node subflow | 0.004489 s | 131.1 KiB |
| Persist 25-node workflow | 0.007942 s | 58.9 KiB |
| Persist 100 node-state updates | 0.754369 s | 10.3 KiB |
| Recover one interrupted run | 0.007445 s | 10.1 KiB |
| Regenerate evidence from result checkpoint | 0.566715 s | 3.10 MiB |

The 100-node browser interaction completed in 10.949 s in the Playwright Chromium
canvas journey (100 sequential accessible palette additions followed by fit-view);
the Python harness intentionally does not invent a browser timing. Evidence
regeneration excludes matching and reuses the existing result state.
