# Milestone 2B Acceptance Matrix

| # | Acceptance criterion | Evidence | Status |
|---:|---|---|---|
| 1 | Compare arbitrary canonical datasets by configurable keys | `test_key_comparison_is_order_independent_and_reports_all_categories` | Pass |
| 2 | Added, removed, modified, unchanged identified | comparison unit test and old/new profile | Pass |
| 3 | Field differences retain both values | comparison contracts and unit tests | Pass |
| 4 | Structure differences are separate | `compare_structures`, structure unit test | Pass |
| 5 | Generic parent-child integrity | composite-key integrity unit test | Pass |
| 6 | Ordered exact, normalised, tolerance, fuzzy stages | reconciliation engine suite | Pass |
| 7 | Matches are consumed between stages | `test_exact_waterfall_consumes_matches_before_later_stages` | Pass |
| 8 | Fuzzy matching is blocked and budgeted | candidate-limit and cancellation tests | Pass |
| 9 | Weighted scores are validated and transparent | weighted contribution unit test | Pass |
| 10 | Ambiguity enters review | fuzzy-tie unit test | Pass |
| 11 | Review events are immutable and superseding | persistence integration test | Pass |
| 12 | Professional evidence outputs | vertical slice and deterministic export test | Pass |
| 13 | Match stage, score, reason, lineage retained | `MatchResult` plus vertical slice | Pass |
| 14 | Background cancellation and recovery | executor/checkpoint suites | Pass |
| 15 | Sources remain unchanged | vertical-slice fingerprint assertions | Pass |
| 16 | M1A/M1B/M2A workflows remain compatible | workflow migration and complete regression suites | Pass |
| 17 | SQLite/workflow migrations tested | migration integration suite | Pass |
| 18 | Required quality gates pass | delivery handoff command record | Pass |

Protected tags `v0.1.0-m1a`, `v0.2.0-m1b`, and `v0.3.0-m2a` remain unchanged.
