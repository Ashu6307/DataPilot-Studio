# ADR-006: Persistent local jobs behind replaceable interfaces

Status: Accepted — 2026-07-17

## Decision

Persist job/event/checkpoint metadata in SQLite behind `JobStore`; execute with an in-process local worker and cooperative batch cancellation. Keep engine execution independent of FastAPI and the persistence implementation.

## Consequences

The local product gains non-blocking runs and restart recovery without prematurely adopting a broker. A future PostgreSQL/distributed worker can implement the same contracts.
