"""Ordered, deterministic reconciliation waterfall with governed review routing."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import polars as pl

from packages.contracts import (
    CandidateEstimate,
    MatchCandidate,
    MatchMethod,
    MatchResult,
    MatchStage,
    ReconciliationResult,
    ReconciliationSummary,
    ReconciliationWorkflow,
    RecordReference,
    ReviewDecision,
    ReviewQueueItem,
    RunStatus,
)
from packages.data_engine.comparison import compare_field
from packages.data_engine.fuzzy_matching import candidate_pairs, generate_fuzzy_candidates
from packages.data_engine.normalisation import normalise_key
from packages.data_engine.tolerance import compare_dates, compare_numeric
from packages.data_engine.weighted_matching import generate_weighted_candidates


def _reference(dataset_id: UUID, row: dict[str, Any], index: int, fields: list[str]) -> RecordReference:
    raw_key = [row.get(field) for field in fields]
    source_row = row.get("__source_row")
    return RecordReference(
        dataset_id=dataset_id,
        record_id=str(source_row if source_row is not None else index + 1),
        source_row=int(source_row) if isinstance(source_row, int) and source_row > 0 else None,
        business_key=raw_key,
    )


def _estimate_all_pairs(
    stage: MatchStage,
    left_count: int,
    right_count: int,
    maximum: int,
) -> CandidateEstimate:
    pairs = left_count * right_count
    return CandidateEstimate(
        stage_id=stage.id,
        left_records=left_count,
        right_records=right_count,
        estimated_pairs=pairs,
        maximum_pairs=maximum,
        estimated_memory_bytes=pairs * 160,
        blocked=pairs > maximum,
        warnings=["Candidate set is not blocked"] if pairs else [],
    )


def _exact_candidates(
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
    left_references: list[RecordReference],
    right_references: list[RecordReference],
    stage: MatchStage,
    maximum_pairs: int,
    cancel: Callable[[], None] | None,
) -> tuple[list[MatchCandidate], CandidateEstimate]:
    pipelines = stage.normalisation_pipelines or [None] * len(stage.left_key_fields)
    right_index: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    for index, row in enumerate(right_rows):
        key = normalise_key([row.get(field) for field in stage.right_key_fields], pipelines)
        if all(value is not None and value != "" for value in key):
            right_index[key].append(index)
    candidates: list[MatchCandidate] = []
    pair_count = 0
    for left_index, row in enumerate(left_rows):
        if cancel is not None and left_index % 250 == 0:
            cancel()
        key = normalise_key([row.get(field) for field in stage.left_key_fields], pipelines)
        for right_index_value in right_index.get(key, []):
            pair_count += 1
            if pair_count > maximum_pairs:
                raise ValueError("RECONCILIATION_CANDIDATE_LIMIT_EXCEEDED")
            candidates.append(
                MatchCandidate(
                    left=left_references[left_index],
                    right=right_references[right_index_value],
                    stage_id=stage.id,
                    method=stage.method,
                    score=Decimal(1),
                    contributing_fields=stage.left_key_fields,
                    reason_code=(
                        "NORMALISED_EXACT_MATCH_CANDIDATE"
                        if stage.method == MatchMethod.NORMALISED_EXACT
                        else "EXACT_MATCH_CANDIDATE"
                    ),
                )
            )
    return candidates, CandidateEstimate(
        stage_id=stage.id,
        left_records=len(left_rows),
        right_records=len(right_rows),
        estimated_pairs=pair_count,
        maximum_pairs=maximum_pairs,
        estimated_memory_bytes=pair_count * 160,
        blocked=False,
    )


def _tolerance_candidates(
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
    left_references: list[RecordReference],
    right_references: list[RecordReference],
    stage: MatchStage,
    workflow: ReconciliationWorkflow,
    cancel: Callable[[], None] | None,
) -> tuple[list[MatchCandidate], CandidateEstimate]:
    if stage.candidate_constraints:
        pairs, estimate = candidate_pairs(
            left_rows,
            right_rows,
            stage.candidate_constraints,
            workflow.budgets,
            stage.id,
            cancel,
        )
    else:
        estimate = _estimate_all_pairs(
            stage,
            len(left_rows),
            len(right_rows),
            workflow.budgets.maximum_candidate_pairs,
        )
        if estimate.blocked:
            raise ValueError("TOLERANCE_CANDIDATE_LIMIT_EXCEEDED")
        pairs = [
            (left_index, right_index, [])
            for left_index in range(len(left_rows))
            for right_index in range(len(right_rows))
        ]
    pipelines = stage.normalisation_pipelines or [None] * len(stage.left_key_fields)
    candidates: list[MatchCandidate] = []
    for pair_index, (left_index, right_index, blocking_evidence) in enumerate(pairs):
        if cancel is not None and pair_index % 250 == 0:
            cancel()
        left_row, right_row = left_rows[left_index], right_rows[right_index]
        passed = True
        scores: list[Decimal] = []
        contributing: list[str] = []
        conflicting: list[str] = []
        for position, (left_field, right_field) in enumerate(
            zip(stage.left_key_fields, stage.right_key_fields, strict=True)
        ):
            left_value, right_value = left_row.get(left_field), right_row.get(right_field)
            if left_field in stage.numeric_tolerances:
                evidence = compare_numeric(left_value, right_value, stage.numeric_tolerances[left_field])
                field_passed = evidence.passed
                tolerance = stage.numeric_tolerances[left_field].tolerance
                score = (
                    Decimal(0)
                    if evidence.absolute_difference is None
                    else Decimal(1)
                    if tolerance == 0 and evidence.absolute_difference == 0
                    else max(Decimal(0), Decimal(1) - evidence.absolute_difference / tolerance)
                    if tolerance > 0
                    else Decimal(0)
                )
            elif left_field in stage.date_tolerances:
                date_evidence = compare_dates(left_value, right_value, stage.date_tolerances[left_field])
                field_passed = date_evidence.passed
                score = Decimal(1) if field_passed else Decimal(0)
            else:
                pipeline = pipelines[position]
                left_key = normalise_key([left_value], [pipeline])
                right_key = normalise_key([right_value], [pipeline])
                field_passed = left_key == right_key and left_key[0] is not None
                score = Decimal(1) if field_passed else Decimal(0)
            passed = passed and field_passed
            scores.append(score)
            (contributing if field_passed else conflicting).append(left_field)
        overall = sum(scores, Decimal(0)) / Decimal(len(scores))
        if passed and overall >= stage.threshold:
            candidates.append(
                MatchCandidate(
                    left=left_references[left_index],
                    right=right_references[right_index],
                    stage_id=stage.id,
                    method=stage.method,
                    score=overall,
                    blocking_evidence=blocking_evidence,
                    contributing_fields=contributing,
                    conflicting_fields=conflicting,
                    reason_code="TOLERANCE_MATCH_CANDIDATE",
                )
            )
    return candidates, estimate


def _snapshot(row: dict[str, Any], fields: list[str], maximum_fields: int) -> dict[str, Any]:
    selected = (
        fields[:maximum_fields]
        if fields
        else sorted(key for key in row if not key.startswith("__"))[:maximum_fields]
    )
    return {field: row.get(field) for field in selected}


def _review_item(
    run_id: UUID,
    candidates: list[MatchCandidate],
    left_row: dict[str, Any],
    right_by_id: dict[str, dict[str, Any]],
    workflow: ReconciliationWorkflow,
    reason: str,
) -> ReviewQueueItem:
    return ReviewQueueItem(
        reconciliation_run_id=run_id,
        left_record=_snapshot(left_row, workflow.evidence_fields, workflow.budgets.maximum_snapshot_fields),
        right_candidates=[
            _snapshot(
                right_by_id[candidate.right.record_id],
                workflow.evidence_fields,
                workflow.budgets.maximum_snapshot_fields,
            )
            for candidate in candidates
        ],
        candidates=candidates,
        match_stage_id=candidates[0].stage_id,
        field_differences=[difference for candidate in candidates for difference in candidate.differences],
        review_reason=reason,
        suggested_decision=ReviewDecision.APPROVE_SUGGESTED if candidates else ReviewDecision.REJECT_ALL,
    )


def _confidence(score: Decimal) -> str:
    if score >= Decimal("0.95"):
        return "high"
    if score >= Decimal("0.80"):
        return "medium"
    return "low"


def reconcile_datasets(
    left: pl.DataFrame,
    right: pl.DataFrame,
    workflow: ReconciliationWorkflow,
    *,
    run_id: UUID | None = None,
    cancel: Callable[[], None] | None = None,
    progress: Callable[[str, int, int, str], None] | None = None,
) -> ReconciliationResult:
    run_identifier = run_id or uuid4()
    required_left = {field for stage in workflow.stages for field in stage.left_key_fields}
    required_right = {field for stage in workflow.stages for field in stage.right_key_fields}
    if required_left - set(left.columns) or required_right - set(right.columns):
        raise ValueError(
            f"RECONCILIATION_KEY_FIELD_MISSING:left={sorted(required_left - set(left.columns))},"
            f"right={sorted(required_right - set(right.columns))}"
        )
    left_rows = list(left.iter_rows(named=True))
    right_rows = list(right.iter_rows(named=True))
    initial_stage = workflow.stages[0]
    left_references = [
        _reference(workflow.left_dataset_id, row, index, initial_stage.left_key_fields)
        for index, row in enumerate(left_rows)
    ]
    right_references = [
        _reference(workflow.right_dataset_id, row, index, initial_stage.right_key_fields)
        for index, row in enumerate(right_rows)
    ]
    left_by_id = {reference.record_id: row for reference, row in zip(left_references, left_rows, strict=True)}
    right_by_id = {reference.record_id: row for reference, row in zip(right_references, right_rows, strict=True)}
    available_left = set(range(len(left_rows)))
    available_right = set(range(len(right_rows)))
    matches: list[MatchResult] = []
    review_items: list[ReviewQueueItem] = []
    estimates: list[CandidateEstimate] = []
    audit: list[str] = []
    for stage_number, stage in enumerate(workflow.stages, 1):
        if cancel is not None:
            cancel()
        selected_left = sorted(available_left)
        selected_right = sorted(available_right)
        stage_left_rows = [left_rows[index] for index in selected_left]
        stage_right_rows = [right_rows[index] for index in selected_right]
        stage_left_refs = [left_references[index] for index in selected_left]
        stage_right_refs = [right_references[index] for index in selected_right]
        if progress is not None:
            progress(stage.id, stage_number - 1, len(workflow.stages), f"Estimating and executing {stage.name}")
        if stage.method in {MatchMethod.EXACT, MatchMethod.NORMALISED_EXACT}:
            candidates, estimate = _exact_candidates(
                stage_left_rows,
                stage_right_rows,
                stage_left_refs,
                stage_right_refs,
                stage,
                workflow.budgets.maximum_candidate_pairs,
                cancel,
            )
        elif stage.method in {
            MatchMethod.NUMERIC_TOLERANCE,
            MatchMethod.DATE_TOLERANCE,
            MatchMethod.COMBINED,
        }:
            candidates, estimate = _tolerance_candidates(
                stage_left_rows,
                stage_right_rows,
                stage_left_refs,
                stage_right_refs,
                stage,
                workflow,
                cancel,
            )
        elif stage.method == MatchMethod.FUZZY_TEXT:
            candidates, estimate = generate_fuzzy_candidates(
                stage_left_rows,
                stage_right_rows,
                stage_left_refs,
                stage_right_refs,
                stage,
                workflow.budgets,
                cancel,
            )
        else:
            candidates, estimate = generate_weighted_candidates(
                stage_left_rows,
                stage_right_rows,
                stage_left_refs,
                stage_right_refs,
                stage,
                workflow.budgets,
                cancel,
            )
        estimates.append(estimate)
        if progress is not None:
            progress(
                stage.id,
                stage_number - 1,
                len(workflow.stages),
                f"Candidate estimate {estimate.estimated_pairs} of {estimate.maximum_pairs}",
            )
        grouped: dict[str, list[MatchCandidate]] = defaultdict(list)
        for candidate in candidates:
            grouped[candidate.left.record_id].append(candidate)
        consumed_right: set[str] = set()
        left_global = {left_references[index].record_id: index for index in selected_left}
        right_global = {right_references[index].record_id: index for index in selected_right}
        for left_id, choices in sorted(grouped.items()):
            choices.sort(key=lambda item: (-item.score, item.right.record_id))
            if len(choices) > workflow.budgets.maximum_duplicate_group_size:
                raise ValueError("RECONCILIATION_DUPLICATE_GROUP_LIMIT_EXCEEDED")
            top_score = choices[0].score
            top = [choice for choice in choices if choice.score == top_score]
            ambiguous = len(top) > 1 or any(choice.tie for choice in top)
            if stage.tie_breaking_rule == "stable_record_id" and ambiguous:
                top = [min(top, key=lambda item: item.right.record_id)]
                ambiguous = False
            available_choices = [choice for choice in top if choice.right.record_id not in consumed_right]
            if stage.one_to_one and not available_choices:
                ambiguous = True
                available_choices = top
            low_confidence = stage.method == MatchMethod.FUZZY_TEXT and top_score < min(
                Decimal(1), stage.threshold + Decimal("0.05")
            )
            if ambiguous or low_confidence or (len(choices) > 1 and stage.tie_breaking_rule == "none"):
                review_items.append(
                    _review_item(
                        run_identifier,
                        choices,
                        left_by_id[left_id],
                        right_by_id,
                        workflow,
                        "Ambiguous, tied, duplicate, or low-confidence candidates require a governed decision",
                    )
                )
                if len(review_items) > workflow.budgets.maximum_review_items:
                    raise ValueError("RECONCILIATION_REVIEW_ITEM_LIMIT_EXCEEDED")
                continue
            selected = available_choices[0]
            selected_left_row = left_by_id[selected.left.record_id]
            selected_right_row = right_by_id[selected.right.record_id]
            pair_differences = []
            for rule in workflow.comparison_fields:
                difference = compare_field(
                    tuple(selected.left.business_key),
                    selected_left_row.get(rule.field_id),
                    selected_right_row.get(rule.field_id),
                    rule,
                )
                if difference is not None:
                    pair_differences.append(difference)
            matches.append(
                MatchResult(
                    left=selected.left,
                    right=selected.right,
                    stage_id=stage.id,
                    match_type=stage.method,
                    score=selected.score,
                    matched_fields=selected.contributing_fields or stage.left_key_fields,
                    differences=pair_differences,
                    reason_code=selected.reason_code,
                    confidence=_confidence(selected.score),
                    review_required=False,
                    field_scores=selected.field_scores,
                )
            )
            consumed_right.add(selected.right.record_id)
            if stage.continue_policy == "remove_matches":
                available_left.discard(left_global[selected.left.record_id])
                available_right.discard(right_global[selected.right.record_id])
        stage_match_count = sum(1 for item in matches if item.stage_id == stage.id)
        stage_review_count = sum(1 for item in review_items if item.match_stage_id == stage.id)
        audit.append(
            f"stage={stage.id};candidates={len(candidates)};matches={stage_match_count};review={stage_review_count}"
        )
        if progress is not None:
            progress(stage.id, stage_number, len(workflow.stages), f"Completed {stage.name}")
    method_counts = Counter(match.match_type for match in matches)
    field_differences = [difference for match in matches for difference in match.differences]
    return ReconciliationResult(
        run_id=run_identifier,
        workflow_id=workflow.id,
        workflow_version=workflow.version,
        status=RunStatus.SUCCEEDED,
        matches=matches,
        review_items=review_items,
        left_unmatched=[left_references[index] for index in sorted(available_left)],
        right_unmatched=[right_references[index] for index in sorted(available_right)],
        field_differences=field_differences,
        stage_estimates=estimates,
        summary=ReconciliationSummary(
            total_left_rows=left.height,
            total_right_rows=right.height,
            matched=len(matches),
            exact_matches=method_counts[MatchMethod.EXACT],
            normalised_matches=method_counts[MatchMethod.NORMALISED_EXACT],
            tolerance_matches=sum(
                method_counts[method]
                for method in {MatchMethod.NUMERIC_TOLERANCE, MatchMethod.DATE_TOLERANCE, MatchMethod.COMBINED}
            ),
            fuzzy_matches=method_counts[MatchMethod.FUZZY_TEXT],
            weighted_matches=method_counts[MatchMethod.WEIGHTED],
            review_pending=len(review_items),
            left_unmatched=len(available_left),
            right_unmatched=len(available_right),
            duplicate_candidates=sum(1 for item in review_items if len(item.candidates) > 1),
        ),
        audit=audit,
    )
