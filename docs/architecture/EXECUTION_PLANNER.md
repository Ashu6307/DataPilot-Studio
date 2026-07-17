# Execution Planner

Planning is pure and deterministic. It validates the graph, resolves typed
parameter defaults/overrides, computes a parameter fingerprint, performs stable
topological ordering, assigns dependency-based parallel groups, counts output
consumers, detects dead ports, and identifies manual/non-retryable nodes.

The plan fingerprint covers workflow identity/version, parameter fingerprint,
planned node details, and declared outputs. Timestamps and canvas-only movement
do not silently change execution semantics. Resource warnings are preserved for
preflight display. The 25-node, 100-node, branching, and subflow cases are
measured by `scripts/benchmark_m3a.py`.
