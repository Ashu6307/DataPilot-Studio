"""Generate deterministic, anonymised Milestone 2A composition fixtures."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "composition"


def _csv(name: str, headers: list[str], rows: list[list[object]]) -> Path:
    path = FIXTURES / name
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)
    return path


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    _csv("same_schema_a.csv", ["employee_id", "department", "amount"], [["E001", "Finance", 10]])
    _csv("same_schema_reordered.csv", ["amount", "employee_id", "department"], [[20, "E002", "Sales"]])
    _csv("renamed_columns.csv", ["emp_code", "dept", "net_value"], [["E003", "Finance", 30]])
    _csv("missing_optional.csv", ["employee_id", "amount"], [["E004", 40]])
    _csv("missing_required.csv", ["department", "amount"], [["Support", 50]])
    _csv("extra_field.csv", ["employee_id", "department", "amount", "notes"], [["E005", "Ops", 60, "extra"]])
    _csv("type_mismatch.csv", ["employee_id", "department", "amount"], [["E006", "Ops", "not-a-number"]])
    duplicate = _csv("duplicate_file_a.csv", ["employee_id", "amount"], [["E007", 70]])
    shutil.copyfile(duplicate, FIXTURES / "duplicate_file_b.csv")
    _csv("duplicate_rows.csv", ["employee_id", "amount"], [["E008", 80], ["E008", 80], ["E009", 90]])
    _csv(
        "join_left.csv",
        ["employee_id", "period", "left_value"],
        [["E001", "2026-01", 1], ["E002", "2026-01", 2], ["E003", "2026-01", 3], [None, "2026-01", 4]],
    )
    _csv(
        "join_right_one.csv",
        ["employee_id", "period", "right_value"],
        [["E001", "2026-01", 10], ["E002", "2026-01", 20], ["E004", "2026-01", 40], [None, "2026-01", 50]],
    )
    _csv(
        "join_right_many.csv",
        ["employee_id", "period", "right_value"],
        [["E001", "2026-01", 10], ["E001", "2026-01", 11], ["E002", "2026-01", 20]],
    )
    _csv(
        "join_left_many.csv",
        ["employee_id", "period", "left_value"],
        [["E001", "2026-01", 1], ["E001", "2026-01", 2], ["E002", "2026-01", 3]],
    )
    _csv("wide_pivot.csv", ["entity", "period", "value"], [["E001", f"P{index:03d}", index] for index in range(1, 261)])
    _csv("unpivot.csv", ["entity", "jan", "feb", "mar"], [["E001", 10, 11, 12], ["E002", 20, "", 22]])
    _csv(
        "invalid_split_values.csv",
        ["department", "month", "value"],
        [["../Finance:North*?", "2026-01", 1], ["Finance/North", "2026-01", 2], ["A" * 80, "2026-02", 3]],
    )
    _csv("duplicate_split_names.csv", ["department", "value"], [["Finance/North", 1], ["Finance\\North", 2]])
    for batch in range(10):
        _csv(
            f"large_append_{batch + 1:02d}.csv",
            ["row_id", "department", "amount"],
            [[batch * 10_000 + row, f"D{row % 20:02d}", row % 1000] for row in range(10_000)],
        )
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "A" * 31
    sheet.append(["split_value", "value"])
    sheet.append(["B" * 80, 1])
    workbook.save(FIXTURES / "excel_sheet_name_limit.xlsx")
    (FIXTURES / "partial_corrupted.xlsx").write_bytes(b"not-an-ooxml-workbook")


if __name__ == "__main__":
    main()
