"""Governed fuzzy candidate generation with mandatory blocking and budgets."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from packages.contracts import (
    BlockingMethod,
    CandidateConstraint,
    CandidateEstimate,
    FuzzyMethod,
    MatchCandidate,
    MatchMethod,
    MatchStage,
    ReconciliationBudgets,
    RecordReference,
)
from packages.data_engine.normalisation import normalise_value
from packages.data_engine.tolerance import as_date, as_decimal


def _normalised_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).casefold().split())


def _levenshtein_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, 1):
        current = [left_index]
        for right_index, right_character in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


def fuzzy_similarity(left: Any, right: Any, method: FuzzyMethod) -> Decimal:
    left_text = _normalised_text(left)[:500]
    right_text = _normalised_text(right)[:500]
    if not left_text and not right_text:
        return Decimal(1)
    if not left_text or not right_text:
        return Decimal(0)
    if method == FuzzyMethod.LEVENSHTEIN:
        distance = _levenshtein_distance(left_text, right_text)
        score = 1 - distance / max(len(left_text), len(right_text))
    elif method == FuzzyMethod.TOKEN_SORT:
        score = SequenceMatcher(None, " ".join(sorted(left_text.split())), " ".join(sorted(right_text.split()))).ratio()
    elif method == FuzzyMethod.TOKEN_SET:
        left_tokens, right_tokens = set(left_text.split()), set(right_text.split())
        union = left_tokens | right_tokens
        score = len(left_tokens & right_tokens) / len(union) if union else 1.0
    else:
        score = SequenceMatcher(None, left_text, right_text).ratio()
    return Decimal(str(score)).quantize(Decimal("0.000001"))


def _constraint_value(row: dict[str, Any], field: str, constraint: CandidateConstraint) -> Any:
    value = row.get(field)
    if constraint.method in {BlockingMethod.EXACT, BlockingMethod.CATEGORY}:
        return _normalised_text(value)
    if constraint.method == BlockingMethod.FIRST_CHARACTER:
        text = _normalised_text(value)
        return text[:1]
    if constraint.method == BlockingMethod.PREFIX:
        length = int(constraint.parameters.get("length", 3))
        if length < 1 or length > 50:
            raise ValueError("FUZZY_PREFIX_LENGTH_INVALID")
        return _normalised_text(value)[:length]
    if constraint.method == BlockingMethod.MONTH:
        parsed = as_date(value)
        return (parsed.year, parsed.month) if parsed else None
    if constraint.method == BlockingMethod.AMOUNT_BUCKET:
        numeric = as_decimal(value)
        width = as_decimal(constraint.parameters.get("width", 100))
        if numeric is None or width is None or width <= 0:
            return None
        return int(numeric // width)
    if constraint.method == BlockingMethod.DATE_WINDOW:
        parsed = as_date(value)
        days = int(constraint.parameters.get("days", 7))
        if parsed is None or days < 1:
            return None
        return parsed.toordinal() // days
    raise ValueError(f"FUZZY_BLOCKING_METHOD_UNSUPPORTED:{constraint.method}")


def candidate_pairs(
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
    constraints: list[CandidateConstraint],
    budgets: ReconciliationBudgets,
    stage_id: str,
    cancel: Callable[[], None] | None = None,
) -> tuple[list[tuple[int, int, list[str]]], CandidateEstimate]:
    if not constraints:
        raise ValueError("FUZZY_BLOCKING_REQUIRED")
    right_blocks: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    for right_index, row in enumerate(right_rows):
        block = tuple(_constraint_value(row, constraint.right_field, constraint) for constraint in constraints)
        if all(value is not None and value != "" for value in block):
            right_blocks[block].append(right_index)
    pairs: list[tuple[int, int, list[str]]] = []
    estimated_pairs = 0
    for left_index, row in enumerate(left_rows):
        if cancel is not None and left_index % 100 == 0:
            cancel()
        block = tuple(_constraint_value(row, constraint.left_field, constraint) for constraint in constraints)
        matches = right_blocks.get(block, [])
        estimated_pairs += len(matches)
        if estimated_pairs > budgets.maximum_candidate_pairs:
            estimate = CandidateEstimate(
                stage_id=stage_id,
                left_records=len(left_rows),
                right_records=len(right_rows),
                estimated_pairs=estimated_pairs,
                maximum_pairs=budgets.maximum_candidate_pairs,
                estimated_memory_bytes=estimated_pairs * 160,
                blocked=True,
                warnings=["Candidate-pair estimate exceeds configured safety budget"],
            )
            raise ValueError(f"FUZZY_CANDIDATE_LIMIT_EXCEEDED:{estimate.model_dump_json()}")
        evidence = [f"{constraint.id}={block[index]}" for index, constraint in enumerate(constraints)]
        pairs.extend((left_index, right_index, evidence) for right_index in matches)
    estimate = CandidateEstimate(
        stage_id=stage_id,
        left_records=len(left_rows),
        right_records=len(right_rows),
        estimated_pairs=estimated_pairs,
        maximum_pairs=budgets.maximum_candidate_pairs,
        estimated_memory_bytes=estimated_pairs * 160,
        blocked=False,
    )
    return pairs, estimate


def generate_fuzzy_candidates(
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
    left_references: list[RecordReference],
    right_references: list[RecordReference],
    stage: MatchStage,
    budgets: ReconciliationBudgets,
    cancel: Callable[[], None] | None = None,
) -> tuple[list[MatchCandidate], CandidateEstimate]:
    pairs, estimate = candidate_pairs(
        left_rows,
        right_rows,
        stage.candidate_constraints,
        budgets,
        stage.id,
        cancel,
    )
    candidates: list[MatchCandidate] = []
    for pair_index, (left_index, right_index, blocking_evidence) in enumerate(pairs):
        if cancel is not None and pair_index % 250 == 0:
            cancel()
        scores: list[Decimal] = []
        contributing: list[str] = []
        conflicting: list[str] = []
        for field in stage.fuzzy_fields:
            left_value = left_rows[left_index].get(field.left_field)
            right_value = right_rows[right_index].get(field.right_field)
            if field.normalisation is not None:
                left_value = normalise_value(left_value, field.normalisation).normalised_value
                right_value = normalise_value(right_value, field.normalisation).normalised_value
            score = fuzzy_similarity(left_value, right_value, field.method)
            scores.append(score)
            label = f"{field.left_field}:{field.method.value}"
            (contributing if score >= field.threshold else conflicting).append(label)
        overall = sum(scores, Decimal(0)) / Decimal(len(scores))
        if overall < stage.threshold or conflicting:
            continue
        candidates.append(
            MatchCandidate(
                left=left_references[left_index],
                right=right_references[right_index],
                stage_id=stage.id,
                method=MatchMethod.FUZZY_TEXT,
                score=overall,
                blocking_evidence=blocking_evidence,
                contributing_fields=contributing,
                conflicting_fields=conflicting,
                reason_code="FUZZY_CANDIDATE_THRESHOLD_PASSED",
            )
        )
    by_left: dict[str, list[MatchCandidate]] = defaultdict(list)
    for candidate in candidates:
        by_left[candidate.left.record_id].append(candidate)
    for values in by_left.values():
        if len(values) > 1:
            top = max(item.score for item in values)
            tied = [item for item in values if item.score == top]
            if len(tied) > 1:
                for item in tied:
                    item.tie = True
                    item.reason_code = "FUZZY_CANDIDATE_SCORE_TIE"
    return candidates, estimate
