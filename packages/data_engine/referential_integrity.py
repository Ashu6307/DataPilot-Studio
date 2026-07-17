"""Configurable parent-child referential-integrity checks for canonical tables."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import polars as pl

from packages.contracts import (
    IntegrityFinding,
    IntegrityResult,
    IntegritySummary,
    RecordReference,
    ReferentialIntegrityConfiguration,
    Severity,
)
from packages.data_engine.normalisation import normalise_key


def _reference(dataset_id: Any, row: dict[str, Any], index: int, key: tuple[Any, ...]) -> RecordReference:
    source_row = row.get("__source_row")
    return RecordReference(
        dataset_id=dataset_id,
        record_id=str(source_row if source_row is not None else index + 1),
        source_row=int(source_row) if isinstance(source_row, int) and source_row > 0 else None,
        business_key=list(key),
    )


def check_referential_integrity(
    parent: pl.DataFrame,
    child: pl.DataFrame,
    configuration: ReferentialIntegrityConfiguration,
) -> IntegrityResult:
    missing_parent_fields = set(configuration.parent_key_fields) - set(parent.columns)
    missing_child_fields = set(configuration.child_reference_fields) - set(child.columns)
    if missing_parent_fields or missing_child_fields:
        raise ValueError(
            f"INTEGRITY_KEY_FIELD_MISSING:parent={sorted(missing_parent_fields)},child={sorted(missing_child_fields)}"
        )
    pipelines = configuration.key_normalisation or [None] * len(configuration.parent_key_fields)
    parent_index: dict[tuple[Any, ...], list[RecordReference]] = defaultdict(list)
    child_index: dict[tuple[Any, ...], list[RecordReference]] = defaultdict(list)
    null_children: list[IntegrityFinding] = []
    for index, row in enumerate(parent.iter_rows(named=True)):
        key = normalise_key([row.get(field) for field in configuration.parent_key_fields], pipelines)
        parent_index[key].append(_reference(configuration.parent_dataset_id, row, index, key))
    for index, row in enumerate(child.iter_rows(named=True)):
        raw = [row.get(field) for field in configuration.child_reference_fields]
        key = normalise_key(raw, pipelines)
        reference = _reference(configuration.child_dataset_id, row, index, key)
        if any(value is None or (isinstance(value, str) and not value.strip()) for value in raw):
            if configuration.null_reference_policy != "allow":
                null_children.append(
                    IntegrityFinding(
                        category="null_child_reference",
                        key=list(key),
                        child_references=[reference],
                        severity=configuration.severity,
                        reason_code="INTEGRITY_NULL_CHILD_REFERENCE",
                    )
                )
            continue
        child_index[key].append(reference)
    findings: list[IntegrityFinding] = list(null_children)
    duplicate_groups = 0
    for key, parents in parent_index.items():
        if len(parents) > 1:
            duplicate_groups += 1
            findings.append(
                IntegrityFinding(
                    category="duplicate_parent_key",
                    key=list(key),
                    parent_references=parents,
                    severity=configuration.severity,
                    reason_code="INTEGRITY_DUPLICATE_PARENT_KEY",
                )
            )
    valid_count = 0
    missing_count = 0
    for key, children in child_index.items():
        parents = parent_index.get(key, [])
        if not parents:
            missing_count += len(children)
            findings.append(
                IntegrityFinding(
                    category="missing_parent_reference",
                    key=list(key),
                    child_references=children,
                    severity=configuration.severity,
                    reason_code="INTEGRITY_PARENT_REFERENCE_MISSING",
                )
            )
        elif len(parents) == 1:
            valid_count += len(children)
            findings.append(
                IntegrityFinding(
                    category="valid_child_reference",
                    key=list(key),
                    parent_references=parents,
                    child_references=children,
                    severity=Severity.INFORMATION,
                    reason_code="INTEGRITY_REFERENCE_VALID",
                )
            )
    parent_without_child = 0
    for key, parents in parent_index.items():
        if key not in child_index:
            parent_without_child += len(parents)
            findings.append(
                IntegrityFinding(
                    category="parent_without_child",
                    key=list(key),
                    parent_references=parents,
                    severity=Severity.INFORMATION,
                    reason_code="INTEGRITY_PARENT_WITHOUT_CHILD_REFERENCE",
                )
            )
    blocked = configuration.failure_action == "block" and any(
        finding.category in {"missing_parent_reference", "duplicate_parent_key", "null_child_reference"}
        for finding in findings
    )
    return IntegrityResult(
        configuration_id=configuration.id,
        configuration_version=configuration.version,
        findings=findings,
        summary=IntegritySummary(
            parent_rows=parent.height,
            child_rows=child.height,
            valid_child_references=valid_count,
            missing_parent_references=missing_count,
            duplicate_parent_key_groups=duplicate_groups,
            null_child_references=len(null_children),
            parents_without_children=parent_without_child,
        ),
        audit=[
            f"parent_fields={','.join(configuration.parent_key_fields)}",
            f"child_fields={','.join(configuration.child_reference_fields)}",
            f"normalisation_pipelines={len(pipelines)}",
        ],
        blocked=blocked,
    )
