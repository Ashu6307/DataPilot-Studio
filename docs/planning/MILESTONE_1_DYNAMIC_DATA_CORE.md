# Milestone 1: Dynamic Data Core — Limited Vertical Slice

Status: limited vertical slice complete — 2026-07-17. Broader PRD Phase 1 remains open as Milestone 1B.

## User journey

Create project → upload arbitrary supported Excel/CSV → inspect sheets/header candidates and warnings → override selection → preview/profile → confirm canonical mappings → add ordered cleaning steps → add validation rules → preview impact → execute → review processed/rejected/errors/audit → download unique workbook → save/reuse workflow → inspect run history.

## Supported initial operations

Cleaning: trim, whitespace normalisation, upper/lower/proper case, non-printable removal, null-like normalisation, rename/select/reorder, blank-row removal, repeated-header removal. Validation: required, type, unique, allowed values, min/max, text length, regex.

## Acceptance tests

- Name-based processing succeeds with changed row count and reordered source columns.
- Header suggestion returns confidence/evidence and can be overridden.
- Leading-zero identifiers remain strings; invalid/ambiguous dates are flagged.
- Each operation is versioned, validates config, supports sample preview, and reports affected rows/audit metadata.
- Findings contain row/field/rule/severity/reason/message/original value.
- Workbook contains all applicable required sheets, filters, frozen headers, safe widths, formats, highlighting, fingerprint, workflow version, run ID, and reconciliation.
- Original fingerprint remains unchanged on success and failure.
- Failed/partial runs cannot appear as succeeded; workflow JSON rejects secret-like content.
- API integration and guided UI E2E journey pass.

## Deliberate limitations

No legacy XLS, password-protected workbook, PDF/database/API/folder connector, multiple simultaneous tables, formula evaluation, arbitrary expressions, true streaming Excel, background scheduling, plugin loading, licensing enforcement, cloud upload, or desktop packaging.

## Verified evidence

- The guided browser journey creates a project, uploads an anonymised CSV, discovers and profiles it, maps fields, applies three cleaning operations and three validations, previews, executes, and exposes the workbook download.
- The saved configuration runs against a reordered-column fixture without processor changes.
- CSV/XLSX title-row, hidden-sheet, manual header override, leading-zero, mixed-type, invalid-date, repeated-header, duplicate, missing, empty, corrupt, differing-count, and 100k-row fixtures are generated deterministically.
- Failure injection records `failed` status and audit evidence in run history; it never reports success.
