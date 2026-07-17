# Background Execution

The local API submits immutable run requests to a `JobStore` and returns immediately. A replaceable local worker claims queued jobs, writes structured progress events, executes engine batches, and persists terminal state. API handlers do not contain processing logic.

Allowed transitions are explicit: queued → running → succeeded/partial/failed; queued/running → cancelling → cancelled/partial/failed. Terminal states cannot transition to succeeded later. Cancellation is cooperative between bounded batches and before publication. Retry creates a new attempt only for explicitly retryable failures.

SQLite is the initial `JobStore`; the interface uses stable job/event/checkpoint contracts so PostgreSQL/distributed workers can replace persistence without rewriting the workflow engine.
