"""Transparent weighted multi-field scoring."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from packages.contracts import (
    CandidateEstimate,
    FieldScore,
    MatchCandidate,
    MatchMethod,
    MatchStage,
    ReconciliationBudgets,
    RecordReference,
    WeightedFieldConfiguration,
)
from packages.data_engine.fuzzy_matching import candidate_pairs, fuzzy_similarity
from packages.data_engine.tolerance import compare_dates, compare_numeric


def _field_score(left: Any, right: Any, field: WeightedFieldConfiguration) -> tuple[Decimal, str]:
    if left is None or right is None:
        if field.missing_value_behavior == "fail":
            return Decimal(0), "WEIGHTED_REQUIRED_VALUE_MISSING"
        return Decimal(0), "WEIGHTED_VALUE_MISSING"
    if field.comparison == "exact":
        score = Decimal(1) if left == right else Decimal(0)
        return score, "WEIGHTED_EXACT_MATCH" if score else "WEIGHTED_EXACT_MISMATCH"
    if field.comparison == "fuzzy":
        if field.fuzzy_method is None:
            raise ValueError("WEIGHTED_FUZZY_METHOD_REQUIRED")
        return fuzzy_similarity(left, right, field.fuzzy_method), "WEIGHTED_FUZZY_SCORE"
    if field.comparison == "numeric_proximity":
        if field.numeric_tolerance is None:
            raise ValueError("WEIGHTED_NUMERIC_TOLERANCE_REQUIRED")
        numeric_evidence = compare_numeric(left, right, field.numeric_tolerance)
        if numeric_evidence.absolute_difference is None:
            return Decimal(0), numeric_evidence.reason_code
        tolerance = field.numeric_tolerance.tolerance
        if tolerance == 0:
            score = Decimal(1) if numeric_evidence.absolute_difference == 0 else Decimal(0)
            return score, numeric_evidence.reason_code
        return (
            max(Decimal(0), Decimal(1) - numeric_evidence.absolute_difference / tolerance),
            numeric_evidence.reason_code,
        )
    if field.date_tolerance is None:
        raise ValueError("WEIGHTED_DATE_TOLERANCE_REQUIRED")
    date_evidence = compare_dates(left, right, field.date_tolerance)
    difference = Decimal(date_evidence.calendar_day_difference or 0)
    days = Decimal(field.date_tolerance.days)
    if days == 0:
        return (Decimal(1) if difference == 0 else Decimal(0)), date_evidence.reason_code
    return max(Decimal(0), Decimal(1) - difference / days), date_evidence.reason_code


def generate_weighted_candidates(
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
    left_references: list[RecordReference],
    right_references: list[RecordReference],
    stage: MatchStage,
    budgets: ReconciliationBudgets,
    cancel: Callable[[], None] | None = None,
) -> tuple[list[MatchCandidate], CandidateEstimate]:
    if stage.candidate_constraints:
        pairs, estimate = candidate_pairs(
            left_rows,
            right_rows,
            stage.candidate_constraints,
            budgets,
            stage.id,
            cancel,
        )
    else:
        pair_count = len(left_rows) * len(right_rows)
        estimate = CandidateEstimate(
            stage_id=stage.id,
            left_records=len(left_rows),
            right_records=len(right_rows),
            estimated_pairs=pair_count,
            maximum_pairs=budgets.maximum_candidate_pairs,
            estimated_memory_bytes=pair_count * 160,
            blocked=pair_count > budgets.maximum_candidate_pairs,
            warnings=["Unblocked weighted candidate set"] if pair_count else [],
        )
        if estimate.blocked:
            raise ValueError("WEIGHTED_CANDIDATE_LIMIT_EXCEEDED")
        pairs = [
            (left_index, right_index, [])
            for left_index in range(len(left_rows))
            for right_index in range(len(right_rows))
        ]
    candidates: list[MatchCandidate] = []
    for pair_index, (left_index, right_index, evidence) in enumerate(pairs):
        if cancel is not None and pair_index % 250 == 0:
            cancel()
        field_scores: list[FieldScore] = []
        missing_ignored = Decimal(0)
        required_failure = False
        for field in stage.weighted_fields:
            left_value = left_rows[left_index].get(field.left_field)
            right_value = right_rows[right_index].get(field.right_field)
            if (left_value is None or right_value is None) and field.missing_value_behavior == "ignore_reweight":
                missing_ignored += field.weight
                continue
            score, reason = _field_score(left_value, right_value, field)
            required_failure = required_failure or (field.required and score == 0)
            field_scores.append(
                FieldScore(
                    field_id=field.id,
                    score=score,
                    weight=field.weight,
                    contribution=score * field.weight,
                    left_value=left_value,
                    right_value=right_value,
                    reason_code=reason,
                )
            )
        denominator = Decimal(1) - missing_ignored
        overall = (
            Decimal(0)
            if denominator <= 0
            else sum((item.contribution for item in field_scores), Decimal(0)) / denominator
        )
        if required_failure or overall < stage.threshold:
            continue
        candidates.append(
            MatchCandidate(
                left=left_references[left_index],
                right=right_references[right_index],
                stage_id=stage.id,
                method=MatchMethod.WEIGHTED,
                score=overall,
                field_scores=field_scores,
                blocking_evidence=evidence,
                contributing_fields=[item.field_id for item in field_scores if item.score > 0],
                conflicting_fields=[item.field_id for item in field_scores if item.score == 0],
                reason_code="WEIGHTED_CANDIDATE_THRESHOLD_PASSED",
            )
        )
    return candidates, estimate
