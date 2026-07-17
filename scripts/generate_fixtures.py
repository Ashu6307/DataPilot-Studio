"""Generate deterministic, anonymised test fixtures. Safe to rerun."""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SAMPLES = ROOT / "samples" / "input"

HEADERS = ["Employee Code", "Full Name", "Status", "Hours", "Work Date"]
ROWS = [
    ["00124", "  anita  rao ", "active", "8", "2026-07-01"],
    ["00125", "VIKRAM  SEN", "active", "9.5", "01/07/2026"],
    ["00125", "Vikram Sen", "paused", "bad", "2026-07-03"],
    ["", "Meera Shah", "active", "7", "2026-07-04"],
]


def write_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        csv.writer(stream).writerows(rows)


def write_workbook(path: Path, title_rows: int = 0, repeated_header: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Attendance import"
    for index in range(title_rows):
        sheet.append([f"Anonymised report title {index + 1}"])
    sheet.append(HEADERS)
    for index, row in enumerate(ROWS):
        sheet.append(row)
        if repeated_header and index == 1:
            sheet.append(HEADERS)
    hidden = workbook.create_sheet("Notes")
    hidden.sheet_state = "hidden"
    hidden.append(["This anonymised sheet is intentionally hidden"])
    workbook.save(path)


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    SAMPLES.mkdir(parents=True, exist_ok=True)
    write_csv(FIXTURES / "header_row_1.csv", [HEADERS, *ROWS])
    reordered = [
        [HEADERS[1], HEADERS[0], *HEADERS[2:]],
        *[[row[1], row[0], *row[2:]] for row in ROWS],
    ]
    write_csv(FIXTURES / "reordered_columns.csv", reordered)
    renamed = ["Staff ID", "Employee Name", "State", "Worked Hours", "Date"]
    write_csv(FIXTURES / "renamed_columns.csv", [renamed, *ROWS])
    write_csv(FIXTURES / "blank_leading_rows.csv", [[], [], HEADERS, *ROWS])
    write_csv(FIXTURES / "repeated_header_rows.csv", [HEADERS, *ROWS[:2], HEADERS, *ROWS[2:]])
    write_csv(FIXTURES / "mixed_values_invalid_dates.csv", [HEADERS, *ROWS])
    write_csv(
        FIXTURES / "different_row_count.csv",
        [HEADERS, *ROWS, ["00128", "New Person", "active", "8", "2026-07-05"]],
    )
    write_csv(FIXTURES / "empty.csv", [])
    (FIXTURES / "corrupted.xlsx").write_bytes(b"This is not an Excel package")
    write_workbook(FIXTURES / "header_after_titles.xlsx", title_rows=3)
    write_workbook(FIXTURES / "repeated_header_hidden_sheet.xlsx", title_rows=2, repeated_header=True)
    write_csv(SAMPLES / "anonymised_attendance.csv", [HEADERS, *ROWS])
    large = FIXTURES / "large_synthetic_100k.csv"
    if not large.exists():
        with large.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(HEADERS)
            for index in range(100_000):
                writer.writerow([f"{index:08d}", f"Person {index}", "active", index % 12, "2026-07-01"])
    print(f"Generated anonymised fixtures in {FIXTURES}")


if __name__ == "__main__":
    main()
