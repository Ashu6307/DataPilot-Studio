"""Safe split naming and deterministic batch evidence packaging."""

from __future__ import annotations

import csv
import json
import re
import zipfile
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import polars as pl
import xlsxwriter

from packages.contracts import (
    BatchCatalog,
    CanonicalType,
    CompositionPlan,
    OutputManifestEntry,
    SchemaAlignmentMatrix,
    SplitConfiguration,
    SplitMode,
)
from packages.data_engine.expressions import EvaluationContext, evaluate_expression, infer_expression_type
from packages.data_engine.safety import sha256_file

INVALID_NAME = re.compile(r"[<>:\"/\\|?*\x00-\x1f]+")
WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


def safe_output_name(value: str, maximum: int = 180) -> str:
    name = INVALID_NAME.sub("_", value).replace("..", "_").strip(" ._") or "output"
    if name.casefold() in WINDOWS_RESERVED:
        name = f"_{name}"
    return name[:maximum].rstrip(" ._") or "output"


def safe_sheet_name(value: str) -> str:
    return safe_output_name(value, 31).replace("[", "_").replace("]", "_").strip("'")[:31] or "Sheet"


def naming_preview(configuration: SplitConfiguration, split_value: str, run_date: str) -> str:
    variables = defaultdict(
        str,
        {
            "project": safe_output_name(configuration.project_label),
            "split_value": safe_output_name(split_value),
            "run_date": run_date,
            "report_type": safe_output_name(configuration.report_type),
            "department": safe_output_name(split_value),
            "month": safe_output_name(split_value),
        },
    )
    try:
        rendered = configuration.naming_template.format_map(variables)
    except (KeyError, ValueError) as error:
        raise ValueError("SPLIT_NAMING_TEMPLATE_INVALID") from error
    return safe_output_name(rendered)


def _split_key(row: dict[str, Any], configuration: SplitConfiguration) -> str:
    if not configuration.fields:
        return "all"
    values = [row.get(field) for field in configuration.fields]
    if configuration.date_part.value != "none" and values:
        text = str(values[0] or "")
        match = re.match(r"^(\d{4})-(\d{2})", text)
        if match:
            year, month = match.groups()
            if configuration.date_part.value == "year":
                values[0] = year
            elif configuration.date_part.value == "month":
                values[0] = f"{year}-{month}"
            else:
                values[0] = f"{year}-Q{(int(month) - 1) // 3 + 1}"
    return "__".join(str(value) if value is not None else "null" for value in values)


def split_table(
    table: pl.DataFrame,
    configuration: SplitConfiguration,
    execution_date: date | None = None,
) -> dict[str, pl.DataFrame]:
    missing = set(configuration.fields) - set(table.columns)
    if missing:
        raise ValueError(f"SPLIT_FIELDS_NOT_FOUND: {sorted(missing)}")
    rows = table.to_dicts()
    if configuration.condition is not None:
        field_types = {name: _canonical_type(dtype) for name, dtype in table.schema.items()}
        if infer_expression_type(configuration.condition, field_types) != CanonicalType.BOOLEAN:
            raise ValueError("SPLIT_CONDITION_MUST_BE_BOOLEAN")
        rows = [
            row
            for row in rows
            if evaluate_expression(
                configuration.condition,
                EvaluationContext(
                    row=row,
                    field_types=field_types,
                    execution_date=execution_date or date.today(),
                ),
            )
            is True
        ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_split_key(row, configuration)].append(row)
    output: dict[str, pl.DataFrame] = {}
    for key, rows in grouped.items():
        if len(rows) < configuration.minimum_group_size:
            continue
        maximum = configuration.maximum_rows_per_file or len(rows)
        for part, start in enumerate(range(0, len(rows), maximum), start=1):
            name = key if len(rows) <= maximum else f"{key}_part_{part}"
            output[name] = pl.DataFrame(rows[start : start + maximum], schema=table.schema)
    return output


def _canonical_type(dtype: pl.DataType) -> CanonicalType:
    if dtype == pl.Boolean:
        return CanonicalType.BOOLEAN
    if dtype == pl.Date:
        return CanonicalType.DATE
    if dtype == pl.Datetime:
        return CanonicalType.DATETIME
    if dtype.is_integer():
        return CanonicalType.INTEGER
    if dtype.is_numeric():
        return CanonicalType.DECIMAL
    return CanonicalType.TEXT


def _write_csv(path: Path, table: pl.DataFrame) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=table.columns)
        writer.writeheader()
        writer.writerows(table.to_dicts())


def _safe_cell(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return "" if value is None else value


def _write_excel(path: Path, sheets: dict[str, pl.DataFrame]) -> None:
    workbook = xlsxwriter.Workbook(path, {"constant_memory": True, "strings_to_formulas": False})
    header = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#17324D"})
    try:
        used: set[str] = set()
        for original_name, table in sheets.items():
            base = safe_sheet_name(original_name)
            name = base
            counter = 2
            while name.casefold() in used:
                suffix = f"_{counter}"
                name = f"{base[: 31 - len(suffix)]}{suffix}"
                counter += 1
            used.add(name.casefold())
            sheet = workbook.add_worksheet(name)
            for column, label in enumerate(table.columns):
                sheet.write(0, column, label, header)
            for row_index, row in enumerate(table.iter_rows(), start=1):
                for column, value in enumerate(row):
                    sheet.write(row_index, column, _safe_cell(value))
            if table.columns:
                sheet.freeze_panes(1, 0)
                sheet.autofilter(0, 0, table.height, len(table.columns) - 1)
    finally:
        workbook.close()


def export_split_outputs(
    output_directory: Path,
    run_id: UUID,
    table: pl.DataFrame,
    configuration: SplitConfiguration,
    execution_date: date | None = None,
) -> list[OutputManifestEntry]:
    output_directory.mkdir(parents=True, exist_ok=True)
    effective_date = execution_date or datetime.now(UTC).date()
    groups = split_table(table, configuration, effective_date)
    run_date = effective_date.isoformat()
    entries: list[OutputManifestEntry] = []
    paths: list[Path] = []
    if configuration.mode == SplitMode.EXCEL_SHEETS:
        destination = output_directory / f"{safe_output_name(configuration.project_label)}_{str(run_id)[:8]}.xlsx"
        _write_excel(destination, groups)
        paths.append(destination)
        entries.append(
            OutputManifestEntry(
                relative_path=destination.name,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                size_bytes=destination.stat().st_size,
                sha256=sha256_file(destination),
                rows=sum(item.height for item in groups.values()),
            )
        )
    else:
        used: set[str] = set()
        for key, group in groups.items():
            base = naming_preview(configuration, key, run_date)
            name = base
            counter = 2
            while name.casefold() in used:
                name = f"{base}_{counter}"
                counter += 1
            used.add(name.casefold())
            suffix = ".csv" if configuration.mode in {SplitMode.CSV_FILES, SplitMode.ZIP_PACKAGE} else ".xlsx"
            destination = (output_directory / f"{name}{suffix}").resolve()
            if output_directory.resolve() not in destination.parents or destination.exists():
                raise FileExistsError("SPLIT_OUTPUT_COLLISION")
            if suffix == ".csv":
                _write_csv(destination, group)
                media_type = "text/csv"
            else:
                _write_excel(destination, {key: group})
                media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            paths.append(destination)
            entries.append(
                OutputManifestEntry(
                    relative_path=destination.name,
                    media_type=media_type,
                    size_bytes=destination.stat().st_size,
                    sha256=sha256_file(destination),
                    rows=group.height,
                    split_key=key,
                )
            )
        if configuration.mode == SplitMode.ZIP_PACKAGE:
            archive = output_directory / f"{safe_output_name(configuration.project_label)}_{str(run_id)[:8]}.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for path in sorted(paths, key=lambda item: item.name.casefold()):
                    info = zipfile.ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    bundle.writestr(info, path.read_bytes())
                manifest_payload = json.dumps(
                    [entry.model_dump(mode="json") for entry in entries], sort_keys=True, indent=2
                ).encode("utf-8")
                info = zipfile.ZipInfo("output-manifest.json", date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(info, manifest_payload)
            entries.append(
                OutputManifestEntry(
                    relative_path=archive.name,
                    media_type="application/zip",
                    size_bytes=archive.stat().st_size,
                    sha256=sha256_file(archive),
                    rows=sum(item.height for item in groups.values()),
                )
            )
    return entries


def export_batch_evidence(
    output_directory: Path,
    run_id: UUID,
    plan: CompositionPlan,
    catalog: BatchCatalog,
    alignment: SchemaAlignmentMatrix,
    processed: pl.DataFrame,
    rejected: pl.DataFrame,
    review: pl.DataFrame,
    warnings: list[str],
    left_unmatched: pl.DataFrame | None = None,
    right_unmatched: pl.DataFrame | None = None,
    create_zip: bool = True,
) -> list[OutputManifestEntry]:
    """Write a deterministic selection of derived evidence; source files are never included."""
    output_directory.mkdir(parents=True, exist_ok=True)
    entries: list[OutputManifestEntry] = []

    def register(path: Path, media_type: str, rows: int = 0) -> None:
        entries.append(
            OutputManifestEntry(
                relative_path=path.name,
                media_type=media_type,
                size_bytes=path.stat().st_size,
                sha256=sha256_file(path),
                rows=rows,
            )
        )

    processed_path = output_directory / "processed-output.csv"
    _write_csv(processed_path, processed)
    register(processed_path, "text/csv", processed.height)
    rejected_path = output_directory / "rejected-rows.csv"
    _write_csv(rejected_path, rejected)
    register(rejected_path, "text/csv", rejected.height)
    review_path = output_directory / "review-rows.csv"
    _write_csv(review_path, review)
    register(review_path, "text/csv", review.height)
    for filename, table in (
        ("left-unmatched.csv", left_unmatched),
        ("right-unmatched.csv", right_unmatched),
    ):
        if table is not None:
            path = output_directory / filename
            _write_csv(path, table)
            register(path, "text/csv", table.height)
    payloads: dict[str, Any] = {
        "schema-alignment.json": alignment.model_dump(mode="json"),
        "batch-summary.json": {
            "run_id": str(run_id),
            "files_considered": catalog.files_considered,
            "files_eligible": catalog.files_eligible,
            "files_quarantined": catalog.files_quarantined,
            "rows_estimated": catalog.total_row_estimate,
            "rows_output": processed.height,
            "rows_rejected": rejected.height,
            "review_rows": review.height,
            "warnings": warnings,
        },
        "source-manifest.json": [item.model_dump(mode="json", exclude={"discovery"}) for item in catalog.items],
        "rejected-files.json": [
            item.model_dump(mode="json", exclude={"discovery"})
            for item in catalog.items
            if not item.processing_eligible
        ],
        "applied-plan.json": plan.model_dump(mode="json"),
        "audit-log.json": {
            "plan_id": str(plan.id),
            "plan_version": plan.version,
            "alignment_plan_id": str(plan.alignment.id),
            "alignment_plan_version": plan.alignment.version,
            "operation": plan.operation,
            "generated_at": datetime.now(UTC).isoformat(),
        },
    }
    for filename, payload in payloads.items():
        path = output_directory / filename
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        register(path, "application/json")
    manifest_path = output_directory / "output-manifest.json"
    manifest_path.write_text(
        json.dumps([item.model_dump(mode="json") for item in entries], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    register(manifest_path, "application/json")
    if create_zip:
        archive = output_directory / f"batch-evidence-{str(run_id)[:8]}.zip"
        included = [output_directory / entry.relative_path for entry in entries]
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(included, key=lambda item: item.name.casefold()):
                info = zipfile.ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(info, path.read_bytes())
        register(archive, "application/zip", processed.height)
    return entries
