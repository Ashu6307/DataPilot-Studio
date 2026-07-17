# Manual Checkpoints

Manual checkpoints cover mapping, schema drift, many-to-many join approval,
reconciliation review, quality thresholds, and output publication. Reaching a
gate stores only minimal evidence summary and sets the node/run to waiting.
Outputs remain unavailable.

Decisions support approve, reject, edit/rerun, skip, and cancel. Events are
append-only; a correction references the superseded event instead of deleting
history. Approval or permitted skip resumes from fingerprinted completed
artifacts. Rejection/cancel cannot be presented as success.
