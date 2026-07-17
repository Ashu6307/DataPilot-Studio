from __future__ import annotations

from scripts.benchmark_m2b import (
    duplicate_groups,
    exact_comparison,
    fuzzy_and_review,
    tolerance_matching,
)


def test_m2b_synthetic_budget_harness_reports_real_counts() -> None:
    exact, result = exact_comparison(500)
    assert exact["candidate_pairs"] == 500
    assert result.summary.unchanged == 500
    fuzzy, (_, reconciliation) = fuzzy_and_review(25)
    assert fuzzy["candidate_pairs"] == 50
    assert reconciliation.summary.review_pending == 25
    tolerance, tolerance_result = tolerance_matching(25)
    assert tolerance["candidate_pairs"] == 25
    assert tolerance_result.summary.tolerance_matches == 25
    duplicates, duplicate_result = duplicate_groups(25)
    assert duplicates["candidate_pairs"] == 0
    assert duplicate_result.summary.duplicate_left_keys == 1
