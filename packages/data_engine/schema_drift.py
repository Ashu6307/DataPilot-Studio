"""Explicit schema-drift analysis and user-controlled mapping repair."""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

from packages.contracts import (
    CanonicalField,
    CanonicalType,
    ColumnMapping,
    DriftCategory,
    DriftFinding,
    DriftPolicy,
    DriftPolicyMode,
    MappingCandidate,
    MappingDecisionAudit,
    MappingMatchMethod,
    MappingRepairAction,
    MappingRepairDecision,
    MappingSet,
    SchemaDriftResult,
    SchemaExpectation,
    TableDiscovery,
)

TOKEN = re.compile(r"[^a-z0-9]+")
DUPLICATE_SUFFIX = re.compile(r"_(\d+)$")


def normalise_label(value: str) -> str:
    return TOKEN.sub("", value.casefold())


def _compatible(expected: CanonicalType, observed: CanonicalType) -> bool:
    if expected == observed or expected == CanonicalType.TEXT:
        return True
    return {expected, observed} <= {CanonicalType.INTEGER, CanonicalType.DECIMAL} or {
        expected,
        observed,
    } <= {CanonicalType.DATE, CanonicalType.DATETIME}


def _candidate(
    field: CanonicalField,
    source_column: str,
    method: MappingMatchMethod,
    confidence: float,
    observed_type: CanonicalType,
    sample_values: list[str],
    evidence: list[str],
) -> MappingCandidate:
    if not _compatible(field.data_type, observed_type):
        confidence = max(0.0, confidence - 0.25)
        evidence = [*evidence, "observed type is not compatible with expected type"]
    else:
        evidence = [*evidence, "observed type is compatible with expected type"]
    if sample_values:
        evidence.append(f"{len(sample_values)} bounded sample value(s) available for review")
    return MappingCandidate(
        source_column=source_column,
        method=method,
        confidence=round(confidence, 3),
        expected_type=field.data_type,
        observed_type=observed_type,
        sample_values=sample_values,
        evidence=evidence,
    )


def _mapping_candidates(
    field: CanonicalField,
    previous_source: str | None,
    table: TableDiscovery,
    synonyms: list[str],
) -> list[MappingCandidate]:
    candidates: dict[str, MappingCandidate] = {}
    aliases = [value for value in [previous_source, *field.aliases] if value]
    for profile in table.columns:
        source = profile.source_name
        source_normalised = normalise_label(source)
        proposed: MappingCandidate | None = None
        if source_normalised == normalise_label(field.id):
            proposed = _candidate(
                field,
                source,
                MappingMatchMethod.CANONICAL_ID,
                1.0,
                profile.inferred_type,
                profile.sample_values,
                ["normalised source label exactly matches canonical field ID"],
            )
        elif any(source.casefold() == alias.casefold() for alias in aliases):
            proposed = _candidate(
                field,
                source,
                MappingMatchMethod.SOURCE_ALIAS,
                0.98,
                profile.inferred_type,
                profile.sample_values,
                ["source label exactly matches a previous/approved alias"],
            )
        elif source_normalised in {normalise_label(field.label), *(normalise_label(item) for item in aliases)}:
            proposed = _candidate(
                field,
                source,
                MappingMatchMethod.NORMALISED_LABEL,
                0.94,
                profile.inferred_type,
                profile.sample_values,
                ["normalised source and expected labels match"],
            )
        elif any(source.casefold() == synonym.casefold() for synonym in synonyms):
            proposed = _candidate(
                field,
                source,
                MappingMatchMethod.APPROVED_SYNONYM,
                0.92,
                profile.inferred_type,
                profile.sample_values,
                ["source label matches an explicitly approved synonym"],
            )
        else:
            reference_labels = [field.label, field.id, *aliases, *synonyms]
            similarity = max(
                (SequenceMatcher(None, source_normalised, normalise_label(item)).ratio() for item in reference_labels),
                default=0.0,
            )
            if similarity >= 0.45:
                score = 0.72 * similarity + (0.18 if _compatible(field.data_type, profile.inferred_type) else 0)
                score += 0.04 if profile.sample_values else 0
                proposed = _candidate(
                    field,
                    source,
                    MappingMatchMethod.TYPE_COMPATIBLE_SIMILARITY,
                    min(score, 0.9),
                    profile.inferred_type,
                    profile.sample_values,
                    [f"normalised label similarity {similarity:.0%}"],
                )
        if proposed is not None:
            existing = candidates.get(source)
            if existing is None or proposed.confidence > existing.confidence:
                candidates[source] = proposed
    return sorted(candidates.values(), key=lambda item: (-item.confidence, item.source_column.casefold()))


def analyze_schema_drift(
    expectation: SchemaExpectation,
    observed: TableDiscovery,
    policy: DriftPolicy | None = None,
) -> SchemaDriftResult:
    active_policy = policy or DriftPolicy()
    findings: list[DriftFinding] = []
    candidate_map: dict[str, list[MappingCandidate]] = {}
    auto_accepted: dict[str, str] = {}
    previous_by_field = {
        item.canonical_field_id: item.source_column for item in expectation.mapping.mappings
    }
    observed_by_name = {item.source_name: item for item in observed.columns}
    used_columns: set[str] = set()

    if expectation.sheet_name and expectation.sheet_name != observed.sheet_name:
        findings.append(
            DriftFinding(
                category=DriftCategory.SHEET_RENAMED,
                expected=expectation.sheet_name,
                observed=observed.sheet_name,
                evidence=["selected sheet label changed"],
            )
        )
    if expectation.header_levels != len(observed.selected_header_rows):
        findings.append(
            DriftFinding(
                category=DriftCategory.HEADER_LEVEL_CHANGED,
                expected=expectation.header_levels,
                observed=len(observed.selected_header_rows),
                evidence=["selected header level count differs from saved expectation"],
            )
        )
    if expectation.start_row and expectation.start_row != observed.start_row or (
        expectation.start_column and expectation.start_column != observed.start_column
    ):
        findings.append(
            DriftFinding(
                category=DriftCategory.SELECTED_TABLE_MOVED,
                expected={"row": expectation.start_row, "column": expectation.start_column},
                observed={"row": observed.start_row, "column": observed.start_column},
                evidence=["selected table start coordinate changed"],
            )
        )

    for field in expectation.mapping.canonical_fields:
        previous = previous_by_field.get(field.id)
        candidates = _mapping_candidates(
            field,
            previous,
            observed,
            expectation.approved_synonyms.get(field.id, []),
        )
        candidate_map[field.id] = candidates
        suggested = candidates[0] if candidates else None
        top = (
            suggested
            if suggested and suggested.confidence >= active_policy.suggestion_threshold
            else None
        )
        ambiguous = bool(
            suggested
            and (
                (suggested.confidence < active_policy.suggestion_threshold and field.required)
                or (
                    top is not None
                    and len(candidates) > 1
                    and suggested.confidence - candidates[1].confidence < active_policy.ambiguity_delta
                )
            )
        )
        if top and not ambiguous:
            used_columns.add(top.source_column)
            if previous and previous != top.source_column:
                findings.append(
                    DriftFinding(
                        category=DriftCategory.COLUMN_RENAMED,
                        canonical_field_id=field.id,
                        expected=previous,
                        observed=top.source_column,
                        confidence=top.confidence,
                        evidence=top.evidence,
                    )
                )
            profile = observed_by_name[top.source_column]
            if not _compatible(field.data_type, profile.inferred_type):
                findings.append(
                    DriftFinding(
                        category=DriftCategory.DATA_TYPE_CHANGED,
                        canonical_field_id=field.id,
                        expected=field.data_type,
                        observed=profile.inferred_type,
                        confidence=top.confidence,
                        evidence=["observed profile type is incompatible with canonical type"],
                        blocking=field.required,
                    )
                )
            if not field.nullable and profile.null_percentage > 0:
                findings.append(
                    DriftFinding(
                        category=DriftCategory.NULLABILITY_CHANGED,
                        canonical_field_id=field.id,
                        expected="non-nullable",
                        observed=f"{profile.null_percentage}% null in bounded profile",
                        evidence=["observed nulls violate saved nullability expectation"],
                        blocking=field.required,
                    )
                )
            allowed = {value.casefold() for value in expectation.allowed_values.get(field.id, [])}
            unexpected = [value for value in profile.sample_values if allowed and value.casefold() not in allowed]
            if unexpected:
                findings.append(
                    DriftFinding(
                        category=DriftCategory.NEW_UNEXPECTED_VALUES,
                        canonical_field_id=field.id,
                        expected=sorted(allowed),
                        observed=unexpected,
                        evidence=["bounded sample contains values outside saved allowed set"],
                    )
                )
            if (
                active_policy.mode == DriftPolicyMode.AUTO_ACCEPT_SAFE
                and top.confidence >= active_policy.safe_accept_threshold
            ):
                auto_accepted[field.id] = top.source_column
        elif ambiguous and suggested:
            findings.append(
                DriftFinding(
                    category=DriftCategory.AMBIGUOUS_MAPPING,
                    canonical_field_id=field.id,
                    expected=previous or field.label,
                    observed=[item.source_column for item in candidates[:3]],
                    confidence=suggested.confidence,
                    evidence=["top mapping is low-confidence or too close to another candidate"],
                    blocking=True,
                )
            )
        else:
            findings.append(
                DriftFinding(
                    category=(
                        DriftCategory.REQUIRED_COLUMN_REMOVED
                        if field.required
                        else DriftCategory.OPTIONAL_COLUMN_REMOVED
                    ),
                    canonical_field_id=field.id,
                    expected=previous or field.label,
                    observed=None,
                    evidence=["no compatible observed source candidate was found"],
                    blocking=field.required,
                )
            )

    observed_order = [item.source_name for item in observed.columns]
    previous_order = [
        source
        for item in expectation.mapping.mappings
        if (source := item.source_column) is not None and source in observed_order
    ]
    if len(previous_order) > 1:
        current_order = sorted(previous_order, key=observed_order.index)
        if current_order != previous_order:
            findings.append(
                DriftFinding(
                    category=DriftCategory.COLUMN_REORDERED,
                    expected=previous_order,
                    observed=current_order,
                    evidence=["same source labels appear in a different order"],
                )
            )
    for column in observed_order:
        if column not in used_columns:
            findings.append(
                DriftFinding(
                    category=DriftCategory.COLUMN_ADDED,
                    observed=column,
                    evidence=["observed column is not selected by any canonical mapping suggestion"],
                )
            )
    duplicate_bases = Counter(
        normalise_label(DUPLICATE_SUFFIX.sub("", column)) for column in observed_order
    )
    for base, count in duplicate_bases.items():
        if base and count > 1:
            findings.append(
                DriftFinding(
                    category=DriftCategory.DUPLICATE_COLUMN_INTRODUCED,
                    observed=base,
                    evidence=[f"{count} observed labels collapse to the same duplicate-disambiguated base"],
                    blocking=True,
                )
            )

    inherently_blocking = any(item.blocking for item in findings)
    blocked = inherently_blocking or (active_policy.mode == DriftPolicyMode.BLOCK and bool(findings))
    requires_confirmation = inherently_blocking or (
        bool(findings) and active_policy.mode in {DriftPolicyMode.REQUIRE_CONFIRMATION, DriftPolicyMode.BLOCK}
    )
    return SchemaDriftResult(
        findings=findings,
        candidates=candidate_map,
        policy=active_policy,
        auto_accepted=auto_accepted,
        requires_confirmation=requires_confirmation,
        blocked=blocked,
        impact_summary=[
            f"{len(findings)} drift finding(s)",
            f"{sum(item.blocking for item in findings)} blocking finding(s)",
            f"{len(auto_accepted)} uniquely safe mapping(s) eligible for automatic acceptance",
        ],
    )


def repair_mapping(
    mapping: MappingSet, decisions: list[MappingRepairDecision]
) -> tuple[MappingSet, MappingDecisionAudit]:
    decision_by_field = {item.canonical_field_id: item for item in decisions}
    mappings: list[ColumnMapping] = []
    for item in mapping.mappings:
        decision = decision_by_field.get(item.canonical_field_id)
        if decision is None or decision.action == MappingRepairAction.REJECT:
            mappings.append(item)
            continue
        mappings.append(
            item.model_copy(
                update={
                    "source_column": decision.selected_source_column,
                    "confidence": decision.suggestion_confidence or 1.0,
                    "user_confirmed": True,
                }
            )
        )
    repaired = mapping.model_copy(update={"version": mapping.version + 1, "mappings": mappings})
    audit = MappingDecisionAudit(
        previous_mapping_version=mapping.version,
        repaired_mapping_version=repaired.version,
        decisions=decisions,
    )
    return repaired, audit
