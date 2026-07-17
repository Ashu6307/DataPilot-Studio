"""Generate deterministic, anonymised M1B demonstration profile assets."""

# ruff: noqa: E501 - narrative fixture text is intentionally readable Markdown.

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from openpyxl import Workbook

from packages.contracts import WorkflowConfiguration

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "samples" / "profiles"


def _id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"datapilot-demo:{name}"))


def _write_csv(path: Path, rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows(rows)


def _literal(value: Any, value_type: str) -> dict[str, Any]:
    return {"kind": "literal", "value": value, "value_type": value_type, "field_id": None, "function": None, "args": []}


def _field(field_id: str) -> dict[str, Any]:
    return {"kind": "field", "value": None, "value_type": None, "field_id": field_id, "function": None, "args": []}


def _call(function: str, *args: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "call",
        "value": None,
        "value_type": None,
        "field_id": None,
        "function": function,
        "args": list(args),
    }


def _calculation(
    profile: str, calculation_id: str, output: str, output_type: str, expression: dict[str, Any], description: str
) -> dict[str, Any]:
    return {
        "calculation_id": calculation_id,
        "version": 1,
        "output_canonical_field": output,
        "output_type": output_type,
        "expression": expression,
        "null_policy": "propagate",
        "error_policy": "reject_row",
        "reason_code": f"{profile.upper()}_{calculation_id.upper().replace('.', '_')}_FAILED",
        "description": description,
        "created_at": "2026-07-17T00:00:00Z",
        "updated_at": "2026-07-17T00:00:00Z",
    }


def _workflow(
    slug: str,
    display_name: str,
    fields: list[dict[str, Any]],
    source_columns: list[str],
    *,
    operations: list[dict[str, Any]] | None = None,
    calculations: list[dict[str, Any]] | None = None,
    validations: list[dict[str, Any]] | None = None,
    discovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "1.1",
        "compatibility_version": 1,
        "id": _id(f"{slug}:workflow"),
        "workflow_version": 1,
        "project_id": _id(f"{slug}:project"),
        "display_name": display_name,
        "source_connector": "file.excel" if slug == "inventory_movement" else "file.csv",
        "discovery_overrides": {
            "sheet_name": None,
            "header_row": 1,
            "header_rows": None,
            "table_id": None,
            "header_search_depth": 25,
            "preview_rows": 25,
            "profile_sample_rows": 10000,
            "max_header_levels": 3,
            "header_flattening_separator": ".",
            **(discovery or {}),
        },
        "mapping": {
            "id": _id(f"{slug}:mapping"),
            "version": 1,
            "canonical_fields": fields,
            "mappings": [
                {
                    "source_column": source,
                    "canonical_field_id": field["id"],
                    "confidence": 1,
                    "user_confirmed": True,
                    "constant_value": None,
                    "default_value": None,
                }
                for source, field in zip(source_columns, fields, strict=True)
            ],
            "created_at": "2026-07-17T00:00:00Z",
            "created_by": "anonymised-demo-generator",
        },
        "operations": operations or [],
        "calculations": calculations or [],
        "validation_rules": validations or [],
        "export": {
            "filename_prefix": slug,
            "include_summary": True,
            "include_rejected_rows": True,
            "include_source_metadata": True,
        },
        "created_at": "2026-07-17T00:00:00Z",
        "updated_at": "2026-07-17T00:00:00Z",
        "change_note": "Anonymised M1B demonstration profile",
    }
    WorkflowConfiguration.model_validate(payload)
    return payload


def _field_contract(
    field_id: str, label: str, data_type: str = "text", *, required: bool = False, aliases: list[str] | None = None
) -> dict[str, Any]:
    return {
        "id": field_id,
        "label": label,
        "data_type": data_type,
        "required": required,
        "nullable": not required,
        "unique": False,
        "aliases": aliases or [],
    }


def _operation(slug: str, index: int, operation_id: str, config: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _id(f"{slug}:operation:{index}"),
        "operation_id": operation_id,
        "operation_version": 1,
        "config": config,
        "enabled": True,
    }


def _write_profile(slug: str, workflow: dict[str, Any], readme: str, walkthrough: str) -> Path:
    root = PROFILES / slug
    root.mkdir(parents=True, exist_ok=True)
    (root / "workflow.json").write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    (root / "README.md").write_text(readme.strip() + "\n", encoding="utf-8")
    (root / "WALKTHROUGH.md").write_text(walkthrough.strip() + "\n", encoding="utf-8")
    return root


def sales_profile() -> None:
    slug = "sales_mis"
    fields = [
        _field_contract("branch_id", "Branch ID", required=True, aliases=["Location ID"]),
        _field_contract("region", "Region", required=True),
        _field_contract("target", "Target", "decimal", required=True),
        _field_contract("actual", "Actual", "decimal", required=True),
    ]
    calculations = [
        _calculation(
            slug,
            "variance",
            "variance",
            "decimal",
            _call("subtract", _field("actual"), _field("target")),
            "Actual minus target",
        ),
        _calculation(
            slug,
            "status",
            "status",
            "text",
            _call(
                "if",
                _call("greater_than", _field("actual"), _field("target")),
                _literal("above_target", "text"),
                _call(
                    "if",
                    _call("equal", _field("actual"), _field("target")),
                    _literal("on_target", "text"),
                    _literal("below_target", "text"),
                ),
            ),
            "Region performance status",
        ),
    ]
    workflow = _workflow(
        slug,
        "Sales MIS region summary",
        fields,
        ["Branch Code", "Region", "Target", "Actual"],
        operations=[
            _operation(
                slug,
                1,
                "group.aggregate",
                {
                    "group_by": ["region"],
                    "aggregates": [
                        {"field_id": "target", "function": "sum", "output_field_id": "target"},
                        {"field_id": "actual", "function": "sum", "output_field_id": "actual"},
                    ],
                },
            )
        ],
        calculations=calculations,
    )
    root = _write_profile(
        slug,
        workflow,
        """# Sales MIS demo

Synthetic branch sales data demonstrates source aliases, canonical mapping, region aggregation, variance, and status calculations. No company names or profile-specific engine code are used.
""",
        """# UI walkthrough

1. Import `input.csv` and confirm the four-column table.
2. Review canonical mappings and numeric types.
3. Preview the generic `group.aggregate` node, then nested variance/status expressions.
4. Run and compare the Processed Data sheet with `expected_output.csv`.
""",
    )
    _write_csv(
        root / "input.csv",
        [
            ["Branch Code", "Region", "Target", "Actual"],
            ["BR-001", "North", 100, 95],
            ["BR-002", "North", 120, 130],
            ["BR-003", "South", 80, 80],
            ["BR-004", "South", 90, 70],
        ],
    )
    _write_csv(
        root / "expected_output.csv",
        [
            ["region", "target", "actual", "variance", "status"],
            ["North", 220, 225, 5, "above_target"],
            ["South", 170, 150, -20, "below_target"],
        ],
    )


def attendance_profile() -> None:
    slug = "hr_attendance"
    fields = [
        _field_contract("employee_id", "Employee ID", required=True, aliases=["Staff ID"]),
        _field_contract("work_date", "Work Date", "date", required=True, aliases=["Date"]),
        _field_contract("status", "Status", required=True, aliases=["Attendance Status"]),
        _field_contract("hours", "Hours", "decimal"),
    ]
    calculation = _calculation(
        slug,
        "attendance_key",
        "attendance_key",
        "text",
        _call("concatenate", _field("employee_id"), _literal("|", "text"), _field("work_date")),
        "Composite Employee ID and Date concept",
    )
    validations = [
        {
            "id": "EMPLOYEE_REQUIRED",
            "rule_type": "required",
            "field_id": "employee_id",
            "severity": "blocking",
            "reason_code": "EMPLOYEE_ID_MISSING",
            "message": "Employee ID is required",
            "config": {},
        },
        {
            "id": "ATTENDANCE_KEY_UNIQUE",
            "rule_type": "unique",
            "field_id": "attendance_key",
            "severity": "error",
            "reason_code": "EMPLOYEE_DATE_DUPLICATE",
            "message": "Employee ID and date must be unique",
            "config": {},
        },
        {
            "id": "STATUS_ALLOWED",
            "rule_type": "allowed_values",
            "field_id": "status",
            "severity": "error",
            "reason_code": "ATTENDANCE_STATUS_INVALID",
            "message": "Attendance status is not allowed",
            "config": {"values": ["present", "absent", "leave"]},
        },
        {
            "id": "DATE_VALID",
            "rule_type": "data_type",
            "field_id": "work_date",
            "severity": "error",
            "reason_code": "WORK_DATE_INVALID",
            "message": "Work date must be an ISO date",
            "config": {"data_type": "date"},
        },
    ]
    workflow = _workflow(
        slug,
        "HR attendance quality",
        fields,
        ["Employee Code", "Work Date", "Status", "Hours"],
        calculations=[calculation],
        validations=validations,
    )
    root = _write_profile(
        slug,
        workflow,
        """# HR Attendance demo

Leading-zero employee IDs remain text. The profile validates ISO dates, required IDs, allowed statuses, and a calculated Employee ID + Date composite uniqueness key.
""",
        """# UI walkthrough

Import `input.csv`, review the leading-zero identifier evidence, inspect the composite-key expression, preview validation findings, and export rejected rows with stable reason codes.
""",
    )
    _write_csv(
        root / "input.csv",
        [
            ["Employee Code", "Work Date", "Status", "Hours"],
            ["0001", "2026-07-01", "present", 8],
            ["0001", "2026-07-01", "present", 8],
            ["0002", "17/07/2026", "paused", 7],
            ["", "2026-07-03", "absent", 0],
        ],
    )
    _write_csv(
        root / "expected_output.csv",
        [
            ["employee_id", "work_date", "status", "hours", "attendance_key", "expected_reason"],
            ["0001", "2026-07-01", "present", 8, "0001|2026-07-01", "EMPLOYEE_DATE_DUPLICATE"],
            ["0002", "17/07/2026", "paused", 7, "0002|17/07/2026", "WORK_DATE_INVALID;ATTENDANCE_STATUS_INVALID"],
            ["", "2026-07-03", "absent", 0, "|2026-07-03", "EMPLOYEE_ID_MISSING"],
        ],
    )


def invoice_profile() -> None:
    slug = "invoice_preparation"
    fields = [
        _field_contract("vendor", "Vendor", required=True, aliases=["Supplier"]),
        _field_contract("invoice_id", "Invoice Number", required=True, aliases=["Invoice No"]),
        _field_contract("amount", "Amount", "decimal", required=True),
        _field_contract("due_date", "Due Date", "date", required=True),
    ]
    calculation = _calculation(
        slug,
        "ageing_days",
        "ageing_days",
        "integer",
        _call("date_difference", _call("today"), _field("due_date")),
        "Age in days from deterministic execution date",
    )
    validations = [
        {
            "id": "AMOUNT_NON_NEGATIVE",
            "rule_type": "min_max",
            "field_id": "amount",
            "severity": "error",
            "reason_code": "INVOICE_AMOUNT_INVALID",
            "message": "Invoice amount must be non-negative",
            "config": {"min": 0},
        }
    ]
    workflow = _workflow(
        slug,
        "Invoice reconciliation preparation",
        fields,
        ["Vendor Name", "Invoice No", "Amount", "Due Date"],
        calculations=[calculation],
        validations=validations,
    )
    root = _write_profile(
        slug,
        workflow,
        """# Invoice Reconciliation Preparation demo

Vendor aliases, text-preserved invoice identifiers, amount validation, due-date ageing, and quality findings are demonstrated. Multi-source reconciliation is explicitly deferred.
""",
        """# UI walkthrough

Import `input.csv`, confirm invoice numbers remain text, review the injected-date ageing expression, preview amount findings, and export the preparation pack. Do not configure a second source in M1B.
""",
    )
    _write_csv(
        root / "input.csv",
        [
            ["Vendor Name", "Invoice No", "Amount", "Due Date"],
            ["Synthetic Vendor A", "000045", 1200, "2026-07-01"],
            ["Synthetic Vendor B", "000046", -5, "2026-07-20"],
        ],
    )
    _write_csv(
        root / "expected_output.csv",
        [
            ["vendor", "invoice_id", "amount", "due_date", "ageing_days", "expected_reason"],
            ["Synthetic Vendor A", "000045", 1200, "2026-07-01", 16, ""],
            ["Synthetic Vendor B", "000046", -5, "2026-07-20", -3, "INVOICE_AMOUNT_INVALID"],
        ],
    )


def inventory_profile() -> None:
    slug = "inventory_movement"
    fields = [
        _field_contract("item_id", "Item ID", required=True),
        _field_contract("warehouse", "Warehouse", required=True),
        _field_contract("opening", "Opening", "decimal", required=True),
        _field_contract("inward", "Inward", "decimal", required=True),
        _field_contract("outward", "Outward", "decimal", required=True),
    ]
    expression = _call("subtract", _call("add", _field("opening"), _field("inward")), _field("outward"))
    calculation = _calculation(
        slug, "calculated_closing", "calculated_closing", "decimal", expression, "Opening plus inward minus outward"
    )
    validations = [
        {
            "id": "NEGATIVE_STOCK",
            "rule_type": "min_max",
            "field_id": "calculated_closing",
            "severity": "error",
            "reason_code": "NEGATIVE_STOCK",
            "message": "Calculated closing stock cannot be negative",
            "config": {"min": 0},
        }
    ]
    workflow = _workflow(
        slug,
        "Inventory movement",
        fields,
        ["Item.Code", "Item.Warehouse", "Movement.Opening", "Movement.Inward", "Movement.Outward"],
        calculations=[calculation],
        validations=validations,
        discovery={"header_row": None, "header_rows": [1, 2]},
    )
    root = _write_profile(
        slug,
        workflow,
        """# Inventory Movement demo

A two-row Excel header proves grouped-header discovery. Canonical item/warehouse mappings feed a safe arithmetic closing-stock calculation and negative-stock validation.
""",
        """# UI walkthrough

Import `input.xlsx`, accept header rows 1–2, inspect flattened labels, review the nested arithmetic tree, and preview the negative-stock finding before export.
""",
    )
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Synthetic movement"
    sheet.append(["Item", "Item", "Movement", "Movement", "Movement"])
    sheet.append(["Code", "Warehouse", "Opening", "Inward", "Outward"])
    sheet.append(["SKU-001", "WH-A", 10, 5, 8])
    sheet.append(["SKU-002", "WH-B", 2, 1, 6])
    workbook.save(root / "input.xlsx")
    _write_csv(
        root / "expected_output.csv",
        [
            ["item_id", "warehouse", "opening", "inward", "outward", "calculated_closing", "expected_reason"],
            ["SKU-001", "WH-A", 10, 5, 8, 7, ""],
            ["SKU-002", "WH-B", 2, 1, 6, -3, "NEGATIVE_STOCK"],
        ],
    )


def consolidation_profile() -> None:
    slug = "generic_monthly_consolidation"
    fields = [
        _field_contract("branch_id", "Branch ID", required=True, aliases=["Location ID"]),
        _field_contract("period", "Period", required=True, aliases=["Month"]),
        _field_contract("sales", "Sales", "decimal", required=True, aliases=["Revenue"]),
    ]
    workflow = _workflow(slug, "Generic monthly canonicalisation", fields, ["Branch Code", "Month", "Sales"])
    root = _write_profile(
        slug,
        workflow,
        """# Generic Monthly Consolidation demo

Two structurally different branch files demonstrate reorder, rename, schema drift review, alias-based mapping repair, and individually canonicalised outputs. Cross-file append remains deferred to Milestone 2.
""",
        """# UI walkthrough

1. Import `branch_a.csv`, confirm exact mappings, and preview canonical output.
2. Reuse the saved workflow with `branch_b.csv`.
3. Review rename/reorder drift, approve Location ID/Period/Revenue aliases, and rerun.
4. Compare both expected canonical files. Do not claim a combined append output in M1B.
""",
    )
    _write_csv(
        root / "branch_a.csv",
        [["Branch Code", "Month", "Sales"], ["BR-001", "2026-06", 100], ["BR-002", "2026-06", 120]],
    )
    _write_csv(
        root / "branch_b.csv",
        [["Revenue", "Location ID", "Period"], [90, "BR-003", "2026-06"], [110, "BR-004", "2026-06"]],
    )
    _write_csv(
        root / "expected_branch_a.csv",
        [["branch_id", "period", "sales"], ["BR-001", "2026-06", 100], ["BR-002", "2026-06", 120]],
    )
    _write_csv(
        root / "expected_branch_b.csv",
        [["branch_id", "period", "sales"], ["BR-003", "2026-06", 90], ["BR-004", "2026-06", 110]],
    )


def main() -> None:
    PROFILES.mkdir(parents=True, exist_ok=True)
    sales_profile()
    attendance_profile()
    invoice_profile()
    inventory_profile()
    consolidation_profile()
    print(f"Generated five anonymised demonstration profiles in {PROFILES}")


if __name__ == "__main__":
    main()
