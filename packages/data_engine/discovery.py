"""Generic CSV/Excel inspection without fixed ranges or business fields."""

from __future__ import annotations

import csv
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from packages.contracts import (
    CanonicalType,
    ColumnProfile,
    DiscoveryOverrides,
    DiscoveryResult,
    HeaderCandidate,
    SourceHandle,
    TableDiscovery,
)
from packages.data_engine.safety import SourceFile

NULL_LIKE = {"", "null", "none", "n/a", "na", "-"}
INTEGER = re.compile(r"^[+-]?\d+$")
DECIMAL = re.compile(r"^[+-]?(?:\d+\.\d+|\d{1,3}(?:,\d{3})+(?:\.\d+)?)$")
DATE_ISO = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
DATE_AMBIGUOUS = re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$")
PERCENT = re.compile(r"^[+-]?\d+(?:\.\d+)?%$")


@dataclass(slots=True)
class RawSheet:
    name: str
    state: str
    rows: list[list[Any]]


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalise_width(rows: list[list[Any]]) -> list[list[Any]]:
    width = max((len(row) for row in rows), default=0)
    return [row + [None] * (width - len(row)) for row in rows]


def _load_csv(path: Path) -> list[RawSheet]:
    raw = path.read_bytes()
    if not raw:
        return [RawSheet(path.stem, "visible", [])]
    encoding = "utf-8-sig"
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError:
        encoding = "cp1252"
        text = raw.decode(encoding)
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [list(row) for row in csv.reader(text.splitlines(), dialect)]
    return [RawSheet(path.stem, "visible", _normalise_width(rows))]


def _load_excel(path: Path) -> list[RawSheet]:
    workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    sheets: list[RawSheet] = []
    try:
        for worksheet in workbook.worksheets:
            rows = [list(row) for row in worksheet.iter_rows(values_only=True)]
            sheets.append(RawSheet(worksheet.title, worksheet.sheet_state, _normalise_width(rows)))
    finally:
        workbook.close()
    return sheets


def load_sheets(source: SourceFile) -> list[RawSheet]:
    suffix = source.path.suffix.lower()
    if suffix == ".csv":
        return _load_csv(source.path)
    if suffix in {".xlsx", ".xlsm"}:
        return _load_excel(source.path)
    raise ValueError(f"SOURCE_UNSUPPORTED_TYPE: {suffix}")


def _is_blank(row: Iterable[Any]) -> bool:
    return not any(_string(value) for value in row)


def _header_score(row: list[Any], following: list[Any] | None) -> tuple[float, list[str]]:
    values = [_string(value) for value in row]
    nonempty = [value for value in values if value]
    if len(nonempty) < 2:
        return 0.0, ["fewer than two non-empty cells"]
    unique_ratio = len(set(value.casefold() for value in nonempty)) / len(nonempty)
    text_ratio = (
        sum(not INTEGER.fullmatch(value) and not DECIMAL.fullmatch(value) for value in nonempty)
        / len(nonempty)
    )
    density = len(nonempty) / max(len(values), 1)
    next_density = (
        0.0
        if following is None
        else sum(bool(_string(value)) for value in following) / max(len(following), 1)
    )
    score = min(1.0, 0.35 * density + 0.3 * unique_ratio + 0.25 * text_ratio + 0.1 * next_density)
    evidence = [
        f"{len(nonempty)} populated labels",
        f"{unique_ratio:.0%} unique labels",
        f"{text_ratio:.0%} text-like labels",
    ]
    return score, evidence


def _candidate_headers(rows: list[list[Any]], depth: int) -> list[HeaderCandidate]:
    candidates: list[HeaderCandidate] = []
    for index, row in enumerate(rows[:depth]):
        following = rows[index + 1] if index + 1 < len(rows) else None
        score, evidence = _header_score(row, following)
        if score >= 0.35:
            labels = [_string(value) for value in row]
            candidates.append(
                HeaderCandidate(
                    row_number=index + 1,
                    confidence=round(score, 3),
                    labels=labels,
                    evidence=evidence,
                )
            )
    return sorted(candidates, key=lambda item: (-item.confidence, item.row_number))[:8]


def _dedupe_headers(row: list[Any]) -> list[str]:
    headers: list[str] = []
    seen: Counter[str] = Counter()
    for index, value in enumerate(row, start=1):
        base = _string(value) or f"unnamed_{index}"
        seen[base.casefold()] += 1
        headers.append(base if seen[base.casefold()] == 1 else f"{base}_{seen[base.casefold()]}")
    return headers


def _infer_type(values: list[str]) -> tuple[CanonicalType, list[str]]:
    present = [value for value in values if value.casefold() not in NULL_LIKE]
    warnings: list[str] = []
    if not present:
        return CanonicalType.TEXT, warnings
    if any(DATE_AMBIGUOUS.fullmatch(value) for value in present):
        warnings.append("Ambiguous date-like values were left as text")
    if all(INTEGER.fullmatch(value) for value in present):
        if any(len(value.lstrip("+-")) > 1 and value.lstrip("+-").startswith("0") for value in present):
            warnings.append("Leading-zero values retained as identifier text")
            return CanonicalType.TEXT, warnings
        return CanonicalType.INTEGER, warnings
    if all(INTEGER.fullmatch(value) or DECIMAL.fullmatch(value) for value in present):
        return CanonicalType.DECIMAL, warnings
    if all(DATE_ISO.fullmatch(value) for value in present):
        return CanonicalType.DATE, warnings
    lowered = {value.casefold() for value in present}
    if lowered <= {"true", "false", "yes", "no"}:
        return CanonicalType.BOOLEAN, warnings
    numeric_count = sum(bool(INTEGER.fullmatch(value) or DECIMAL.fullmatch(value)) for value in present)
    if 0 < numeric_count < len(present):
        warnings.append("Mixed text and numeric values were left as text")
    return CanonicalType.TEXT, warnings


def _semantic_roles(name: str, values: list[str], inferred: CanonicalType) -> list[str]:
    roles: list[str] = []
    token = name.casefold()
    if any(word in token for word in ("id", "code", "number", "no", "ref")):
        roles.append("identifier")
    if inferred in {CanonicalType.DATE, CanonicalType.DATETIME} or "date" in token:
        roles.append("date")
    if inferred == CanonicalType.DECIMAL or any(word in token for word in ("amount", "value", "price", "total")):
        roles.append("amount")
    if "percent" in token or "pct" in token or any(PERCENT.fullmatch(value) for value in values):
        roles.append("percentage")
    if any(word in token for word in ("status", "category", "type")):
        roles.append("category")
    return list(dict.fromkeys(roles))


def _profile(headers: list[str], rows: list[list[Any]]) -> list[ColumnProfile]:
    result: list[ColumnProfile] = []
    row_count = len(rows)
    for index, name in enumerate(headers):
        values = [_string(row[index]) if index < len(row) else "" for row in rows]
        present = [value for value in values if value.casefold() not in NULL_LIKE]
        counts = Counter(present)
        inferred, warnings = _infer_type(values)
        roles = _semantic_roles(name, present[:100], inferred)
        unique_count = len(counts)
        duplicate_count = sum(count - 1 for count in counts.values() if count > 1)
        identifier = "identifier" in roles or any(
            len(value) > 1 and value.startswith("0") for value in present[:100]
        )
        result.append(
            ColumnProfile(
                source_name=name,
                inferred_type=inferred,
                null_percentage=round((row_count - len(present)) * 100 / row_count, 2) if row_count else 0,
                unique_count=unique_count,
                duplicate_count=duplicate_count,
                sample_values=list(dict.fromkeys(present))[:5],
                semantic_roles=roles,
                is_identifier_candidate=identifier,
                is_key_candidate=bool(present) and unique_count == len(present) and len(present) == row_count,
                warnings=warnings,
            )
        )
    return result


def _sheet_discovery(sheet: RawSheet, overrides: DiscoveryOverrides) -> TableDiscovery:
    rows = sheet.rows
    blank_leading = next((index for index, row in enumerate(rows) if not _is_blank(row)), len(rows))
    blank_trailing = next((index for index, row in enumerate(reversed(rows)) if not _is_blank(row)), len(rows))
    candidates = _candidate_headers(rows, overrides.header_search_depth)
    selected = overrides.header_row or (candidates[0].row_number if candidates else max(1, blank_leading + 1))
    if not rows or selected > len(rows):
        headers: list[str] = []
        data_rows: list[list[Any]] = []
    else:
        headers = _dedupe_headers(rows[selected - 1])
        end = len(rows) - blank_trailing if blank_trailing else len(rows)
        data_rows = rows[selected:end]
    repeated = [
        index + selected + 1
        for index, row in enumerate(data_rows)
        if [_string(value).casefold() for value in row[: len(headers)]]
        == [header.casefold() for header in headers]
    ]
    footer_rows: list[int] = []
    for index, row in enumerate(data_rows):
        first = _string(row[0]).casefold() if row else ""
        if first in {"total", "grand total", "subtotal"}:
            footer_rows.append(index + selected + 1)
    profiles = _profile(headers, data_rows)
    preview = [
        dict(zip(headers, [_string(value) for value in row], strict=False))
        for row in data_rows[: overrides.preview_rows]
    ]
    warnings: list[str] = []
    if not rows:
        warnings.append("Source table is empty")
    if not candidates:
        warnings.append("No confident header candidate was found; user confirmation is required")
    if repeated:
        warnings.append(f"Detected {len(repeated)} repeated header row(s)")
    if footer_rows:
        warnings.append(f"Detected {len(footer_rows)} possible footer/total row(s)")
    if len(candidates) > 1 and candidates[0].confidence - candidates[1].confidence < 0.08:
        warnings.append("Header selection is ambiguous")
    width = len(headers)
    region = f"A1:{get_column_letter(max(width, 1))}{max(len(rows), 1)}"
    confidence = candidates[0].confidence if candidates else 0
    return TableDiscovery(
        table_id=f"sheet:{sheet.name}",
        sheet_name=sheet.name,
        sheet_state=sheet.state,
        candidate_region=region,
        candidate_headers=candidates,
        selected_header_row=selected,
        row_count_estimate=len(data_rows),
        column_count=width,
        blank_leading_rows=blank_leading,
        blank_trailing_rows=blank_trailing,
        repeated_header_rows=repeated,
        footer_rows=footer_rows,
        columns=profiles,
        preview=preview,
        confidence=confidence,
        warnings=warnings,
    )


def discover_source(source: SourceFile, handle: SourceHandle, overrides: DiscoveryOverrides) -> DiscoveryResult:
    source.assert_unchanged()
    sheets = load_sheets(source)
    selected_sheets = [sheet for sheet in sheets if overrides.sheet_name in (None, sheet.name)]
    if overrides.sheet_name and not selected_sheets:
        raise ValueError(f"SHEET_NOT_FOUND: {overrides.sheet_name}")
    tables = [_sheet_discovery(sheet, overrides) for sheet in selected_sheets]
    warnings = [] if tables else ["No sheets or tables were found"]
    source.assert_unchanged()
    return DiscoveryResult(source=handle, tables=tables, warnings=warnings)


def read_selected_table(source: SourceFile, overrides: DiscoveryOverrides, limit: int | None = None) -> pl.DataFrame:
    sheets = load_sheets(source)
    sheet = next((item for item in sheets if overrides.sheet_name in (None, item.name)), None)
    if sheet is None:
        raise ValueError("SHEET_NOT_FOUND")
    discovery = _sheet_discovery(sheet, overrides)
    if not discovery.columns:
        return pl.DataFrame()
    header_row = discovery.selected_header_row
    headers = [column.source_name for column in discovery.columns]
    rows = sheet.rows[header_row:]
    if limit is not None:
        rows = rows[:limit]
    records = [
        {header: _string(row[index]) if index < len(row) else "" for index, header in enumerate(headers)}
        for row in rows
    ]
    return pl.DataFrame(records, schema={header: pl.String for header in headers})
