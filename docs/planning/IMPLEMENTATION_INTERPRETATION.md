# Implementation Interpretation and Open Questions

Date: 2026-07-17. Authority: Commercial PRD v1.0 plus the attached milestone brief.

## Interpretation

“Milestone 0” corresponds to PRD Phase 0 and must end with executable contracts, safety utilities, repositories, fixture library, and a sample workflow test harness—not documentation alone. The requested “limited Milestone 1 vertical slice” selects P1-E01 through P1-E06 and P1-E08 through P1-E10, with only the simplest calculated/default field support from P1-E07.

The 15 named UI screens are stages/views in one guided workflow. Separate routable views are not required to prove the slice; no future visual workflow designer, scheduler, licensing console, or reconciliation studio will be presented as finished.

Discovery is generic and overrideable. “Detect” means return a candidate, confidence, evidence, and warnings—not guarantee correctness for every spreadsheet. The first slice supports CSV, XLSX, and non-macro-modifying XLSM reading. Legacy XLS, password-protected, macro-preserving edits, multiple independent regions, and formula evaluation are unsupported with explicit errors/warnings.

Blocking validation findings reject affected rows and make a run partial rather than successful publication. Error findings also reject rows; information/warning findings remain attached to processed rows. This policy is versioned in the workflow.

## Assumptions

- Product name remains DataPilot Studio.
- Windows-first development, local-only processing, Excel/CSV first, and no remote AI are approved.
- A synchronous API run is acceptable for the small initial slice; status and cancellation contracts precede a background worker.
- SQLite is single-user local metadata. Authentication/RBAC begins with team/cloud work.
- Current package versions are pinned after registry verification; lockfiles capture transitive versions.

## Open questions for later gates

1. What supported hardware and time/memory thresholds define 100k-row acceptance?
2. Should validation `Error` always reject, or be configurable independently from severity?
3. Which Excel versions and locale combinations form the formal compatibility matrix?
4. Which credential vault and desktop shell will the commercial Windows release use?
5. What retention defaults apply to uploads, run snapshots, and failed artifacts?
6. Which operation/version migration support window is commercially promised?

None blocks the local foundation because current behaviour is conservative, explicit, and versioned.

