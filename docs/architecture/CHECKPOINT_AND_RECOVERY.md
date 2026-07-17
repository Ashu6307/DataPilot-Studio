# Checkpoint and Recovery

Checkpoints are isolated under the run directory and contain no database row payloads. Metadata records job, workflow/config hash, source fingerprint, completed node/batch, artifact path/hash, row counters, and creation time.

A checkpoint is resumable only when source fingerprint, workflow version/config hash, engine compatibility, and operation semantics match. Non-idempotent or externally side-effecting operations are not retryable. Partial outputs stay quarantined until all publication gates pass.

At startup, jobs left `running` or `cancelling` become recoverable-orphan records. Valid checkpoints may be explicitly resumed; otherwise jobs fail with an actionable recovery code. Retention cleanup never touches source inputs or published outputs.
