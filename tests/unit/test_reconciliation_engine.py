from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import polars as pl
import pytest

from packages.contracts import (
    BlockingMethod,
    BusinessCalendar,
    CandidateConstraint,
    CanonicalField,
    CanonicalType,
    ColumnMapping,
    ColumnProfile,
    ComparisonCategory,
    ComparisonConfiguration,
    DateTolerance,
    DateToleranceMode,
    DuplicateMatchPolicy,
    FieldComparisonRule,
    FuzzyFieldConfiguration,
    FuzzyMethod,
    MappingSet,
    MatchMethod,
    MatchStage,
    NormalisationOperation,
    NormalisationOperationId,
    NormalisationPipeline,
    NumericTolerance,
    NumericToleranceMode,
    ReconciliationBudgets,
    ReconciliationWorkflow,
    ReferentialIntegrityConfiguration,
    SchemaExpectation,
    StructureDifferenceCategory,
    TableDiscovery,
    WeightedFieldConfiguration,
)
from packages.data_engine.comparison import compare_datasets, compare_structures
from packages.data_engine.fuzzy_matching import candidate_pairs, fuzzy_similarity
from packages.data_engine.normalisation import normalise_value
from packages.data_engine.reconciliation import reconcile_datasets
from packages.data_engine.referential_integrity import check_referential_integrity
from packages.data_engine.tolerance import compare_dates, compare_numeric
from packages.workflow_schema import assert_secret_free


def pipeline(*operations: NormalisationOperation) -> NormalisationPipeline:
    return NormalisationPipeline(operations=list(operations))


def test_normalisation_preserves_original_and_audits_each_operation() -> None:
    configured = pipeline(
        NormalisationOperation(operation_id=NormalisationOperationId.TRIM_WHITESPACE),
        NormalisationOperation(operation_id=NormalisationOperationId.COLLAPSE_SPACES),
        NormalisationOperation(operation_id=NormalisationOperationId.UPPERCASE),
        NormalisationOperation(
            operation_id=NormalisationOperationId.REMOVE_PUNCTUATION,
        ),
    )
    audit = normalise_value("  ab-  001  ", configured)
    assert audit.original_value == "  ab-  001  "
    assert audit.normalised_value == "AB 001"
    assert len(audit.steps) == 4
    assert all(step.operation_version == 1 for step in audit.steps)


def test_reconciliation_configuration_rejects_plain_text_secret_material() -> None:
    workflow = ReconciliationWorkflow(
        project_id=uuid4(),
        display_name="Secret scan",
        left_dataset_id=uuid4(),
        right_dataset_id=uuid4(),
        stages=[
            MatchStage(
                id="exact",
                name="Exact",
                priority=1,
                left_key_fields=["key"],
                right_key_fields=["key"],
                method=MatchMethod.EXACT,
                candidate_constraints=[],
            )
        ],
    )
    payload = workflow.model_dump(mode="json")
    payload["stages"][0]["candidate_constraints"] = [
        {
            "id": "unsafe",
            "method": "exact",
            "left_field": "key",
            "right_field": "key",
            "parameters": {"api_key": "plain-text-value"},
        }
    ]
    with pytest.raises(ValueError, match="plain-text secret field is forbidden"):
        assert_secret_free(payload)


def test_leading_zero_normalisation_requires_explicit_approval() -> None:
    configured = pipeline(
        NormalisationOperation(
            operation_id=NormalisationOperationId.NORMALISE_LEADING_ZEROS,
        )
    )
    with pytest.raises(ValueError, match="REQUIRES_APPROVAL"):
        normalise_value("0007", configured)
    approved = pipeline(
        NormalisationOperation(
            operation_id=NormalisationOperationId.NORMALISE_LEADING_ZEROS,
            parameters={"approved": True},
        )
    )
    assert normalise_value("0007", approved).normalised_value == "7"


def test_decimal_and_date_tolerances_cover_boundaries() -> None:
    absolute = NumericTolerance(mode=NumericToleranceMode.ABSOLUTE, tolerance=Decimal("0.10"))
    assert compare_numeric("-10.00", "-10.10", absolute).passed
    assert not compare_numeric("0", "0.11", absolute).passed
    percentage = NumericTolerance(mode=NumericToleranceMode.PERCENTAGE, tolerance=Decimal("5"))
    assert compare_numeric("100", "105", percentage).passed
    calendar = DateTolerance(mode=DateToleranceMode.CALENDAR_DAYS, days=2)
    assert compare_dates("2026-01-01", "2026-01-03", calendar).passed
    business = DateTolerance(
        mode=DateToleranceMode.BUSINESS_DAYS,
        days=1,
        calendar=BusinessCalendar(holidays=[]),
    )
    assert compare_dates("2026-01-02", "2026-01-05", business).passed
    assert compare_dates(
        "2026-01-01", "2026-01-31", DateTolerance(mode=DateToleranceMode.MONTH)
    ).passed
    assert compare_dates(
        "2026-01-15",
        "2026-01-31",
        DateTolerance(mode=DateToleranceMode.PERIOD, period_format="%Y-%m"),
    ).passed


def test_structure_comparison_reuses_schema_drift_and_reports_key_uniqueness() -> None:
    expectation = SchemaExpectation(
        mapping=MappingSet(
            canonical_fields=[
                CanonicalField(id="record_id", label="Record ID", nullable=False),
                CanonicalField(
                    id="amount",
                    label="Amount",
                    data_type=CanonicalType.DECIMAL,
                ),
            ],
            mappings=[
                ColumnMapping(source_column="Record ID", canonical_field_id="record_id"),
                ColumnMapping(source_column="Amount", canonical_field_id="amount"),
            ],
        )
    )
    observed = TableDiscovery(
        table_id="table",
        sheet_name="data",
        candidate_region="A1:C2",
        candidate_headers=[],
        selected_header_row=1,
        selected_header_rows=[1],
        row_count_estimate=1,
        column_count=3,
        blank_leading_rows=0,
        blank_trailing_rows=0,
        columns=[
            ColumnProfile(
                source_name="Record ID",
                inferred_type="text",
                null_percentage=0,
                unique_count=1,
                duplicate_count=0,
                sample_values=["A"],
            ),
            ColumnProfile(
                source_name="Amount",
                inferred_type="text",
                null_percentage=0,
                unique_count=1,
                duplicate_count=0,
                sample_values=["10.00"],
            ),
            ColumnProfile(
                source_name="Unexpected",
                inferred_type="text",
                null_percentage=0,
                unique_count=1,
                duplicate_count=0,
                sample_values=["new"],
            ),
        ],
        preview=[],
        confidence=1,
    )
    result = compare_structures(
        expectation,
        observed,
        expected_key_unique=True,
        observed_key_unique=False,
    )
    categories = {difference.category for difference in result.differences}
    assert StructureDifferenceCategory.ADDED_COLUMN in categories
    assert StructureDifferenceCategory.DATA_TYPE_CHANGED in categories
    assert StructureDifferenceCategory.KEY_UNIQUENESS_CHANGED in categories
    assert not result.compatible


def test_key_comparison_is_order_independent_and_reports_all_categories() -> None:
    left = pl.DataFrame(
        {
            "record_key": ["001", "002", "003", "004", None, "004"],
            "amount": [10, 20, 30, 40, 50, 41],
            "label": ["Same", "Old", "Removed", "Duplicate", "Invalid", "Duplicate"],
        }
    )
    right = pl.DataFrame(
        {
            "label": ["Added", "Same", "New", "Duplicate", "Duplicate"],
            "amount": [90, 10, 22, 40, 42],
            "record_key": ["005", "001", "002", "004", "004"],
        }
    )
    configuration = ComparisonConfiguration(
        project_id=uuid4(),
        left_dataset_id=uuid4(),
        right_dataset_id=uuid4(),
        business_key_fields=["record_key"],
        duplicate_key_policy=DuplicateMatchPolicy.REPORT,
        compare_fields=["amount", "label"],
    )
    result = compare_datasets(left, right, configuration)
    categories = {record.category for record in result.records}
    assert {
        ComparisonCategory.ADDED_RIGHT,
        ComparisonCategory.REMOVED_RIGHT,
        ComparisonCategory.MODIFIED,
        ComparisonCategory.UNCHANGED,
        ComparisonCategory.DUPLICATE_LEFT,
        ComparisonCategory.DUPLICATE_RIGHT,
        ComparisonCategory.INVALID_KEY,
        ComparisonCategory.AMBIGUOUS,
    } <= categories
    assert result.summary.total_left_rows == 6
    assert result.summary.total_right_rows == 5
    assert {difference.field_id for difference in result.field_differences} == {"amount", "label"}


def test_comparison_tolerance_suppresses_immaterial_difference() -> None:
    configuration = ComparisonConfiguration(
        project_id=uuid4(),
        left_dataset_id=uuid4(),
        right_dataset_id=uuid4(),
        business_key_fields=["key"],
        comparison_rules=[
            FieldComparisonRule(
                field_id="amount",
                numeric_tolerance=NumericTolerance(
                    mode=NumericToleranceMode.CURRENCY,
                    tolerance=Decimal("0.01"),
                ),
            )
        ],
        compare_fields=["amount"],
    )
    result = compare_datasets(
        pl.DataFrame({"key": ["01"], "amount": [0.1 + 0.2]}),
        pl.DataFrame({"key": ["01"], "amount": [0.3]}),
        configuration,
    )
    assert result.summary.unchanged == 1


def test_referential_integrity_supports_composite_keys() -> None:
    parent = pl.DataFrame({"part_a": ["01", "02", "02"], "part_b": ["A", "B", "B"]})
    child = pl.DataFrame(
        {"ref_a": ["01", "03", None], "ref_b": ["A", "C", "A"]}
    )
    configuration = ReferentialIntegrityConfiguration(
        project_id=uuid4(),
        parent_dataset_id=uuid4(),
        child_dataset_id=uuid4(),
        parent_key_fields=["part_a", "part_b"],
        child_reference_fields=["ref_a", "ref_b"],
    )
    result = check_referential_integrity(parent, child, configuration)
    assert result.summary.valid_child_references == 1
    assert result.summary.missing_parent_references == 1
    assert result.summary.null_child_references == 1
    assert result.summary.duplicate_parent_key_groups == 1


def test_exact_waterfall_consumes_matches_before_later_stages() -> None:
    left_id, right_id = uuid4(), uuid4()
    workflow = ReconciliationWorkflow(
        project_id=uuid4(),
        display_name="Generic exact waterfall",
        left_dataset_id=left_id,
        right_dataset_id=right_id,
        stages=[
            MatchStage(
                id="exact_primary",
                name="Exact primary",
                priority=1,
                left_key_fields=["key"],
                right_key_fields=["key"],
                method=MatchMethod.EXACT,
            ),
            MatchStage(
                id="exact_secondary",
                name="Exact secondary",
                priority=2,
                left_key_fields=["alternate"],
                right_key_fields=["alternate"],
                method=MatchMethod.EXACT,
            ),
        ],
    )
    result = reconcile_datasets(
        pl.DataFrame({"key": ["A", "B"], "alternate": ["X", "Y"]}),
        pl.DataFrame({"key": ["A", "C"], "alternate": ["X", "Y"]}),
        workflow,
    )
    assert result.summary.matched == 2
    assert [match.stage_id for match in result.matches] == ["exact_primary", "exact_secondary"]
    assert result.summary.left_unmatched == 0
    assert result.summary.right_unmatched == 0


def test_fuzzy_candidates_require_blocking_and_detect_budget_breach() -> None:
    budgets = ReconciliationBudgets(maximum_candidate_pairs=1)
    constraint = CandidateConstraint(
        id="same_region",
        method=BlockingMethod.EXACT,
        left_field="region",
        right_field="region",
    )
    with pytest.raises(ValueError, match="FUZZY_CANDIDATE_LIMIT_EXCEEDED"):
        candidate_pairs(
            [{"region": "n"}, {"region": "n"}],
            [{"region": "n"}, {"region": "n"}],
            [constraint],
            budgets,
            "fuzzy",
        )
    assert fuzzy_similarity("Alpha North", "North Alpha", FuzzyMethod.TOKEN_SORT) == Decimal("1.000000")


def test_fuzzy_tie_routes_to_manual_review() -> None:
    workflow = ReconciliationWorkflow(
        project_id=uuid4(),
        display_name="Generic fuzzy review",
        left_dataset_id=uuid4(),
        right_dataset_id=uuid4(),
        evidence_fields=["name", "region"],
        stages=[
            MatchStage(
                id="fuzzy_name",
                name="Fuzzy name",
                priority=1,
                left_key_fields=["name"],
                right_key_fields=["name"],
                method=MatchMethod.FUZZY_TEXT,
                threshold=Decimal("0.8"),
                candidate_constraints=[
                    CandidateConstraint(
                        id="same_region",
                        method=BlockingMethod.EXACT,
                        left_field="region",
                        right_field="region",
                    )
                ],
                fuzzy_fields=[
                    FuzzyFieldConfiguration(
                        left_field="name",
                        right_field="name",
                        method=FuzzyMethod.NORMALISED,
                        threshold=Decimal("0.8"),
                    )
                ],
            )
        ],
    )
    result = reconcile_datasets(
        pl.DataFrame({"name": ["alpha"], "region": ["north"]}),
        pl.DataFrame({"name": ["alpha", "alpha"], "region": ["north", "north"]}),
        workflow,
    )
    assert result.summary.matched == 0
    assert result.summary.review_pending == 1
    assert result.review_items[0].left_record == {"name": "alpha", "region": "north"}


def test_cancellation_is_observed_inside_fuzzy_candidate_generation() -> None:
    workflow = ReconciliationWorkflow(
        project_id=uuid4(),
        display_name="Cancelled fuzzy stage",
        left_dataset_id=uuid4(),
        right_dataset_id=uuid4(),
        stages=[
            MatchStage(
                id="fuzzy_cancel",
                name="Fuzzy cancel",
                priority=1,
                left_key_fields=["name"],
                right_key_fields=["name"],
                method=MatchMethod.FUZZY_TEXT,
                threshold=Decimal("0.8"),
                candidate_constraints=[
                    CandidateConstraint(
                        id="same_region",
                        method=BlockingMethod.EXACT,
                        left_field="region",
                        right_field="region",
                    )
                ],
                fuzzy_fields=[
                    FuzzyFieldConfiguration(
                        left_field="name",
                        right_field="name",
                        method=FuzzyMethod.NORMALISED,
                        threshold=Decimal("0.8"),
                    )
                ],
            )
        ],
    )
    calls = 0

    def cancel() -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("cancelled during fuzzy stage")

    with pytest.raises(RuntimeError, match="cancelled during fuzzy stage"):
        reconcile_datasets(
            pl.DataFrame({"name": ["alpha"] * 300, "region": ["north"] * 300}),
            pl.DataFrame({"name": ["alpha"] * 2, "region": ["north"] * 2}),
            workflow,
            cancel=cancel,
        )


def test_weighted_score_exposes_per_field_contribution() -> None:
    workflow = ReconciliationWorkflow(
        project_id=uuid4(),
        display_name="Transparent weighted stage",
        left_dataset_id=uuid4(),
        right_dataset_id=uuid4(),
        stages=[
            MatchStage(
                id="weighted",
                name="Weighted",
                priority=1,
                left_key_fields=["name"],
                right_key_fields=["name"],
                method=MatchMethod.WEIGHTED,
                threshold=Decimal("0.7"),
                candidate_constraints=[
                    CandidateConstraint(
                        id="same_region",
                        method=BlockingMethod.EXACT,
                        left_field="region",
                        right_field="region",
                    )
                ],
                weighted_fields=[
                    WeightedFieldConfiguration(
                        id="name_score",
                        left_field="name",
                        right_field="name",
                        comparison="fuzzy",
                        fuzzy_method=FuzzyMethod.NORMALISED,
                        weight=Decimal("0.7"),
                    ),
                    WeightedFieldConfiguration(
                        id="region_score",
                        left_field="region",
                        right_field="region",
                        comparison="exact",
                        weight=Decimal("0.3"),
                    ),
                ],
            )
        ],
    )
    result = reconcile_datasets(
        pl.DataFrame({"name": ["alpha one"], "region": ["north"]}),
        pl.DataFrame({"name": ["alpha 1"], "region": ["north"]}),
        workflow,
    )
    assert result.summary.weighted_matches == 1
    assert len(result.matches[0].field_scores) == 2
    assert sum((item.contribution for item in result.matches[0].field_scores), Decimal(0)) == result.matches[0].score
