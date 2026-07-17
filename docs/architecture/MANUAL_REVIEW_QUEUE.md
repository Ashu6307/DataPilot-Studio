# Manual Review Queue

Review items store only configured evidence fields, bounded by
`maximum_snapshot_fields`, plus candidate references, scores, differences, stage,
reason, suggestion, status, and audit IDs. Raw uploaded datasets are not stored in
SQLite.

Supported decisions are suggested/alternate approval, reject all, mark duplicate,
defer, and escalate. A decision is append-only. A correction supplies
`supersedes_event_id`; the original event remains, and an event cannot be
superseded twice. Alternate approvals must identify a candidate in the review
item. Review history is returned in creation order.
