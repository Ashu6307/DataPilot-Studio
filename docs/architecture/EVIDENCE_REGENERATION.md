# Evidence Regeneration

M2B evidence can be regenerated after review decisions without rerunning
matching. The service loads the fingerprinted `ReconciliationResult`, refreshes
review items from immutable decision events, and calls the existing safe
reconciliation exporter into a new `vN` directory.

Each `EvidencePackageVersion` links the prior package, workflow/run version,
review-decision count, actor, affected output node, reused stage checkpoints,
manifest path, and SHA-256. Existing packages are never overwritten. Formula
injection protection and deterministic ZIP timestamps remain inherited from the
M2B exporter.
