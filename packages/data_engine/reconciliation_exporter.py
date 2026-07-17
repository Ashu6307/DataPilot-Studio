"""Professional, formula-safe reconciliation evidence exports."""

from __future__ import annotations

import csv
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import xlsxwriter

from packages.contracts import (
    IntegrityResult,
    MatchMethod,
    ReconciliationExportEntry,
    ReconciliationExportManifest,
    ReconciliationResult,
    ReconciliationWorkflow,
    ReviewQueueItem,
)
from packages.data_engine.batch_exporter import safe_output_name, safe_sheet_name
from packages.data_engine.safety import sha256_file


def _safe_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, sort_keys=True, default=str)
    if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = sorted({key for row in rows for key in row}) or ["status"]
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: _safe_value(row.get(header)) for header in headers})


def _write_workbook(path: Path, outputs: dict[str, list[dict[str, Any]]]) -> None:
    workbook = xlsxwriter.Workbook(path, {"constant_memory": True, "strings_to_formulas": False})
    workbook.set_properties({"title": "DataPilot reconciliation evidence", "created": datetime(1980, 1, 1, tzinfo=UTC)})
    heading = workbook.add_format(
        {"bold": True, "font_color": "#FFFFFF", "bg_color": "#17324D", "border": 1}
    )
    date_format = workbook.add_format({"num_format": "yyyy-mm-dd"})
    used: set[str] = set()
    try:
        for classification, rows in outputs.items():
            base = safe_sheet_name(classification)
            name = base
            suffix = 2
            while name.casefold() in used:
                marker = f"_{suffix}"
                name = f"{base[: 31 - len(marker)]}{marker}"
                suffix += 1
            used.add(name.casefold())
            worksheet = workbook.add_worksheet(name)
            headers = sorted({key for row in rows for key in row}) or ["status"]
            for column, header in enumerate(headers):
                worksheet.write(0, column, header, heading)
            for row_index, row in enumerate(rows, 1):
                for column, header in enumerate(headers):
                    value = _safe_value(row.get(header))
                    if isinstance(value, datetime):
                        worksheet.write_datetime(row_index, column, value.replace(tzinfo=None), date_format)
                    else:
                        worksheet.write(row_index, column, value)
            worksheet.freeze_panes(1, 0)
            worksheet.autofilter(0, 0, max(1, len(rows)), len(headers) - 1)
            for column, header in enumerate(headers):
                width = min(48, max(12, len(header) + 2))
                worksheet.set_column(column, column, width)
    finally:
        workbook.close()


def _match_row(result: ReconciliationResult, workflow: ReconciliationWorkflow, index: int) -> dict[str, Any]:
    match = result.matches[index]
    return {
        "run_id": str(result.run_id),
        "workflow_id": str(result.workflow_id),
        "workflow_version": workflow.version,
        "left_dataset_id": str(match.left.dataset_id),
        "left_record_id": match.left.record_id,
        "left_source_row": match.left.source_row,
        "right_dataset_id": str(match.right.dataset_id),
        "right_record_id": match.right.record_id,
        "right_source_row": match.right.source_row,
        "business_key": match.left.business_key,
        "match_classification": match.match_type.value,
        "stage_id": match.stage_id,
        "score": str(match.score),
        "reason_code": match.reason_code,
        "confidence": match.confidence,
        "review_required": match.review_required,
    }


def _context(result: ReconciliationResult, workflow: ReconciliationWorkflow) -> dict[str, Any]:
    return {
        "run_id": str(result.run_id),
        "workflow_id": str(result.workflow_id),
        "workflow_version": workflow.version,
        "left_dataset_id": str(workflow.left_dataset_id),
        "right_dataset_id": str(workflow.right_dataset_id),
    }


def _review_row(
    result: ReconciliationResult,
    workflow: ReconciliationWorkflow,
    item: ReviewQueueItem,
) -> dict[str, Any]:
    candidate_references = [
        {
            "left": candidate.left.model_dump(mode="json"),
            "right": candidate.right.model_dump(mode="json"),
            "score": str(candidate.score),
        }
        for candidate in item.candidates
    ]
    return {
        **_context(result, workflow),
        "review_item_id": str(item.id),
        "stage_id": item.match_stage_id,
        "match_classification": f"manual_review_{item.status.value}",
        "status": item.status.value,
        "reason": item.review_reason,
        "candidate_count": len(item.candidates),
        "business_key": item.candidates[0].left.business_key if item.candidates else [],
        "candidate_references": candidate_references,
        "left_record": item.left_record,
        "right_candidates": item.right_candidates,
        "reason_code": "RECONCILIATION_MANUAL_REVIEW_REQUIRED",
    }


def _output_rows(
    result: ReconciliationResult,
    workflow: ReconciliationWorkflow,
    integrity: IntegrityResult | None,
) -> dict[str, list[dict[str, Any]]]:
    context = _context(result, workflow)
    match_rows = [_match_row(result, workflow, index) for index in range(len(result.matches))]
    by_method = {
        method: [row for row in match_rows if row["match_classification"] == method.value]
        for method in MatchMethod
    }
    outputs: dict[str, list[dict[str, Any]]] = {
        "Reconciliation Summary": [
            {
                **context,
                "match_classification": "reconciliation_summary",
                "stage_id": "run",
                "reason_code": "RECONCILIATION_SUMMARY",
                **result.summary.model_dump(mode="json"),
            }
        ],
        "Exact Matches": by_method[MatchMethod.EXACT],
        "Normalised Matches": by_method[MatchMethod.NORMALISED_EXACT],
        "Tolerance Matches": [
            row
            for method in {MatchMethod.NUMERIC_TOLERANCE, MatchMethod.DATE_TOLERANCE, MatchMethod.COMBINED}
            for row in by_method[method]
        ],
        "Fuzzy Matches": by_method[MatchMethod.FUZZY_TEXT],
        "Weighted Matches": by_method[MatchMethod.WEIGHTED],
        "Manual Review Pending": [
            _review_row(result, workflow, item)
            for item in result.review_items
            if item.status.value in {"pending", "deferred", "escalated"}
        ],
        "Manual Review Approved": [
            _review_row(result, workflow, item)
            for item in result.review_items
            if item.status.value == "approved"
        ],
        "Manual Review Rejected": [
            _review_row(result, workflow, item)
            for item in result.review_items
            if item.status.value == "rejected"
        ],
        "Left Unmatched": [
            {
                **context,
                "source_dataset_id": str(reference.dataset_id),
                "source_record_id": reference.record_id,
                "source_row": reference.source_row,
                "business_key": reference.business_key,
                "match_classification": "left_unmatched",
                "stage_id": "unmatched",
                "reason_code": "RECONCILIATION_LEFT_UNMATCHED",
            }
            for reference in result.left_unmatched
        ],
        "Right Unmatched": [
            {
                **context,
                "source_dataset_id": str(reference.dataset_id),
                "source_record_id": reference.record_id,
                "source_row": reference.source_row,
                "business_key": reference.business_key,
                "match_classification": "right_unmatched",
                "stage_id": "unmatched",
                "reason_code": "RECONCILIATION_RIGHT_UNMATCHED",
            }
            for reference in result.right_unmatched
        ],
        "Duplicate Candidates": [
            _review_row(result, workflow, item)
            for item in result.review_items
            if len(item.candidates) > 1
        ],
        "Field Differences": [
            {
                **context,
                "left_source_record_id": match.left.record_id,
                "left_source_row": match.left.source_row,
                "right_source_record_id": match.right.record_id,
                "right_source_row": match.right.source_row,
                "business_key": difference.business_key,
                "match_classification": match.match_type.value,
                "stage_id": match.stage_id,
                **difference.model_dump(mode="json"),
            }
            for match in result.matches
            for difference in match.differences
        ],
        "Referential Integrity Errors": (
            [
                {
                    **context,
                    "match_classification": "referential_integrity_error",
                    "stage_id": "referential_integrity",
                    **finding.model_dump(mode="json"),
                }
                for finding in integrity.findings
                if finding.category != "valid_child_reference"
            ]
            if integrity is not None
            else []
        ),
        "Match Stage Audit": [
            {
                **context,
                "match_classification": "candidate_estimate",
                "reason_code": "RECONCILIATION_CANDIDATE_ESTIMATE",
                **estimate.model_dump(mode="json"),
            }
            for estimate in result.stage_estimates
        ],
        "Applied Rules": [
            {
                **context,
                "stage_id": stage.id,
                "match_classification": "applied_rule",
                "reason_code": "RECONCILIATION_RULE_APPLIED",
                **stage.model_dump(mode="json"),
            }
            for stage in workflow.stages
        ],
        "Run Audit": [
            {
                **context,
                "event": event,
                "match_classification": "run_audit",
                "stage_id": "run",
                "reason_code": "RECONCILIATION_AUDIT_EVENT",
            }
            for event in result.audit
        ],
    }
    if result.comparison_result is not None:
        outputs["Comparison Records"] = [
            {
                **context,
                "match_classification": record.category.value,
                "stage_id": "comparison",
                **record.model_dump(mode="json"),
            }
            for record in result.comparison_result.records
        ]
        outputs["Comparison Field Differences"] = [
            {
                **context,
                "match_classification": "comparison_field_difference",
                "stage_id": "comparison",
                **difference.model_dump(mode="json"),
            }
            for difference in result.comparison_result.field_differences
        ]
    if workflow.export.include_outputs:
        selected = set(workflow.export.include_outputs)
        outputs = {name: rows for name, rows in outputs.items() if name in selected}
    return outputs


def export_reconciliation_evidence(
    output_directory: Path,
    result: ReconciliationResult,
    workflow: ReconciliationWorkflow,
    integrity: IntegrityResult | None = None,
) -> ReconciliationExportManifest:
    output_directory.mkdir(parents=True, exist_ok=True)
    outputs = _output_rows(result, workflow, integrity)
    if len(outputs) > workflow.budgets.maximum_export_sheets:
        raise ValueError("RECONCILIATION_EXPORT_SHEET_LIMIT_EXCEEDED")
    if any(len(rows) > workflow.budgets.maximum_export_rows_per_sheet for rows in outputs.values()):
        raise ValueError("RECONCILIATION_EXPORT_ROW_LIMIT_EXCEEDED")
    entries: list[ReconciliationExportEntry] = []

    def register(path: Path, media_type: str, row_count: int, classification: str) -> None:
        entries.append(
            ReconciliationExportEntry(
                relative_path=path.relative_to(output_directory).as_posix(),
                media_type=media_type,
                size_bytes=path.stat().st_size,
                sha256=sha256_file(path),
                row_count=row_count,
                classification=classification,
            )
        )

    prefix = safe_output_name(workflow.export.filename_prefix)
    if "csv" in workflow.export.formats:
        csv_directory = output_directory / "csv"
        csv_directory.mkdir(exist_ok=False)
        for classification, rows in outputs.items():
            path = csv_directory / f"{safe_output_name(classification)}.csv"
            _write_csv(path, rows)
            register(path, "text/csv", len(rows), classification)
    if "excel" in workflow.export.formats:
        workbook_path = output_directory / f"{prefix}.xlsx"
        _write_workbook(workbook_path, outputs)
        register(
            workbook_path,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            sum(len(rows) for rows in outputs.values()),
            "evidence_workbook",
        )
    if "json" in workflow.export.formats:
        result_path = output_directory / "reconciliation-result.json"
        result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        json.loads(result_path.read_text(encoding="utf-8"))
        register(result_path, "application/json", len(result.matches), "reconciliation_result")
    manifest = ReconciliationExportManifest(
        run_id=result.run_id,
        workflow_id=workflow.id,
        workflow_version=workflow.version,
        status=result.status,
        source_dataset_ids=[workflow.left_dataset_id, workflow.right_dataset_id],
        entries=entries,
        output_counts={name: len(rows) for name, rows in outputs.items()},
        applied_rule_ids=[stage.id for stage in workflow.stages],
        created_at=datetime(1980, 1, 1, tzinfo=UTC),
    )
    manifest_path = output_directory / "reconciliation-manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    if "zip" in workflow.export.formats:
        archive = output_directory / f"{prefix}.zip"
        included = [output_directory / entry.relative_path for entry in entries] + [manifest_path]
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for path in sorted(included, key=lambda item: item.relative_to(output_directory).as_posix()):
                name = path.relative_to(output_directory).as_posix()
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                package.writestr(info, path.read_bytes())
    return manifest
