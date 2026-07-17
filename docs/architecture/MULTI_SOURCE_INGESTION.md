# Multi-source Ingestion

`scan_folder_paths` performs a deterministic, read-only walk from an explicit local
root. Recursion, include/exclude glob patterns, supported suffixes, and maximum file
count are configuration. Each candidate is resolved relative to the root and hashed.

The API imports eligible paths through the existing immutable workspace boundary.
`build_batch_catalog` then invokes normal discovery independently for every file,
selects the first visible or largest table by configured policy, and records schema,
row estimate, warnings, fingerprint, and eligibility. Duplicate fingerprints,
previously processed fingerprints, and failed discovery become explicit states.

The catalog never assumes common sheet names, headers, ranges, column order, or
schema. Input bytes are absent from SQLite and output packages.
