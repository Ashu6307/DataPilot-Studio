# Workflow DAG Architecture

`DagWorkflow` is a versioned, serialisable directed acyclic graph. Nodes carry a
stable type ID/version, typed ports, closed configuration, retry/checkpoint
classification, entitlement capability ID, position, and resource estimates.
Edges name both ports and their artifact contract; row position is never an
implicit key.

Static validation runs before planning and again before execution. The planner
uses a stable topological order, dependency list, parallel group, consumer count,
dead-output analysis, manual gates, and SHA-256 fingerprints. Execution consumes
the immutable plan snapshot rather than canvas order.

The graph layer orchestrates only. DataFrames and engine results live in process
and in fingerprinted run artifacts. SQLite records definitions, plans, state,
paths, hashes, and minimal evidence, not source rows.
