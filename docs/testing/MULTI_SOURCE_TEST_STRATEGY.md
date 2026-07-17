# Multi-source Test Strategy

Testing is layered:

- Unit: scans/patterns/fingerprints, alignment policy, six append duplicate modes,
  six joins and cardinalities, nine aggregates, pivot/unpivot, split conditions,
  filename/sheet safety, deterministic packages.
- Integration: SQLite v3 migration, audited alignment decisions, heterogeneous
  two-source vertical slice, manifests, lineage, source immutability, and existing
  workflow compatibility.
- Background: progress, checkpoints, cancellation, retry eligibility, and orphan
  recovery use the M1B persisted executor contract.
- UI/E2E: the fourteen Composition Studio states, keyboard-reachable controls,
  responsive layout, preview, progress, partial/failure messaging, and manifest.
- Performance: reproducible 100k append/join/pivot/split scenarios with exact data
  shape, hardware, wall time, and Python allocation caveat.

Fixtures are anonymised and generated deterministically. Corrupt inputs must
quarantine; cancelled jobs are state fixtures and never masquerade as files.
