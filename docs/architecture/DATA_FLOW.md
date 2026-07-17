# Data Flow

## Vertical slice

1. The user creates a project; SQLite stores only IDs, names, locale, privacy mode, and timestamps.
2. Upload streams to a generated source ID below `.datapilot/uploads/`; the API rejects unsupported extensions and sanitises the filename.
3. SHA-256 and size are recorded. The connector inspects CSV or workbook metadata without modifying the source.
4. Discovery evaluates rows up to configurable search depth, returning sheets, visibility, candidate headers/regions, samples, profiles, confidence, evidence, and warnings.
5. User overrides select the table/header and confirm source-to-canonical mappings.
6. A versioned workflow stores source settings without paths/data, mapping versions, ordered cleaning nodes, validation rules, export settings, and compatibility version.
7. Preview reads the selected table, applies canonical mapping, operations, and validation to a bounded sample; each step emits metrics.
8. Full run creates `.datapilot/runs/<timestamp>_<run-id>/`, snapshots the workflow, fingerprints source, executes, and exports to `outputs/`.
9. The workbook and `manifest.json` are reopened/verified. Source is re-fingerprinted. Only then can the run become `succeeded`; blocking findings produce `partial`, and exceptions produce `failed`.
10. SQLite stores counts, durations, warnings/errors, operation metrics, fingerprints, and artifact paths—not row data.

## Row reconciliation

`rows_read = rows_written + rows_rejected + rows_filtered`. In the initial slice, non-blocking findings remain in processed output; rows with error/blocking findings are rejected. Filtering is limited to explicit row-removal operations. A mismatch is a run failure.

## Trust boundaries

Browser filenames are untrusted; upload handles are generated server-side. Workflow expressions are restricted configurations, never evaluated as Python. Regex is bounded to Python's supported engine and reviewed as a later denial-of-service hardening item. Output paths are generated under the run root.

