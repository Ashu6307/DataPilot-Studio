# Milestone 3A Acceptance Matrix

| Requirement | Evidence | Status |
|---|---|---|
| Arbitrary typed DAG | `DagWorkflow`, nodes, ports, edges | Pass |
| Closed versioned node registry | `workflow_dag/registry.py` | Pass |
| Cycle, reachability, ports, cardinality, limits | `validate_dag` tests | Pass |
| Runtime parameters and secret references | parameter resolver tests | Pass |
| Visual infinite canvas and palette | `WorkflowStudio.tsx`, Playwright | Pass |
| Deterministic plan/fingerprint | planner tests and benchmark | Pass |
| Background execution only | `LocalDagExecutor.submit` API | Pass |
| Safe ready-node parallelism | parallel-source barrier test | Pass |
| Cancellation and failed/partial isolation | runtime status model and tests | Pass |
| Restart recovery | orphan recovery integration test | Pass |
| Conditional/skipped branches | closed expression adapter and skip state | Pass |
| Reusable version-pinned subflows | expansion and recursion tests | Pass |
| Manual checkpoint decisions | pause/resume integration test | Pass |
| Review-aware evidence regeneration | versioned regeneration service | Pass |
| Version create/clone/publish/restore/diff | API routes and diff tests | Pass |
| Five documented anonymised templates | `samples/dag_templates` test | Pass |
| Workflow migration 1.3 to 1.4 | migration integration test | Pass |
| Database migrations 4 to 5 to 6 | backup/rollback migration tests | Pass |
| Existing M1/M2 compatibility | complete Python/frontend suites | Pass |
| Security scans and final gates | final gate log in milestone handoff | Pass |

“Pass” means implemented with automated evidence. The final gate log is recorded
in the milestone handoff and includes regression, static, browser, dependency,
security, and whitespace checks.
