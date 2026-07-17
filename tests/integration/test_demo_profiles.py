from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from packages.contracts import ReconciliationWorkflow, SourceHandle, WorkflowConfiguration
from packages.data_engine import EngineRuntime, Workspace

ROOT = Path("samples/profiles")
PROFILE_NAMES = {
    "sales_mis",
    "hr_attendance",
    "invoice_preparation",
    "inventory_movement",
    "generic_monthly_consolidation",
}
RECONCILIATION_PROFILE_NAMES = {
    "old_new_report_comparison",
    "vendor_invoice_reconciliation",
    "attendance_master_integrity",
    "inventory_system_reconciliation",
    "customer_deduplication_preparation",
}


def _workflow(profile: str) -> WorkflowConfiguration:
    return WorkflowConfiguration.model_validate_json((ROOT / profile / "workflow.json").read_text(encoding="utf-8"))


def _preview(profile: str, input_name: str, tmp_path: Path):
    workflow = _workflow(profile)
    workspace = Workspace(tmp_path / profile / input_name.replace(".", "_"))
    input_path = ROOT / profile / input_name
    source = workspace.import_source(input_path, input_path.name)
    handle = SourceHandle(
        id=source.id,
        project_id=workflow.project_id,
        original_filename=source.original_filename,
        media_type="application/octet-stream",
        size_bytes=source.size_bytes,
        sha256=source.sha256,
    )
    result = EngineRuntime(workspace, execution_date=date(2026, 7, 17)).preview(source, workflow, limit=100)
    return handle, result


def test_all_five_profiles_are_complete_anonymised_and_valid() -> None:
    assert {path.name for path in ROOT.iterdir() if path.is_dir()} >= PROFILE_NAMES
    for profile in PROFILE_NAMES:
        root = ROOT / profile
        assert (root / "README.md").exists()
        assert (root / "WALKTHROUGH.md").exists()
        assert "walkthrough" in (root / "WALKTHROUGH.md").read_text(encoding="utf-8").casefold()
        workflow = _workflow(profile)
        assert workflow.schema_version == "1.1"
        assert workflow.compatibility_version == 1
        assert isinstance(workflow.id, UUID)
        serialised = json.dumps(workflow.model_dump(mode="json")).casefold()
        assert "private limited" not in serialised
        assert "pvt ltd" not in serialised


def test_all_five_reconciliation_profiles_are_anonymised_and_valid() -> None:
    assert {path.name for path in ROOT.iterdir() if path.is_dir()} >= RECONCILIATION_PROFILE_NAMES
    for profile in RECONCILIATION_PROFILE_NAMES:
        root = ROOT / profile
        assert (root / "README.md").exists()
        assert (root / "left.csv").exists()
        assert (root / "right.csv").exists()
        workflow = ReconciliationWorkflow.model_validate_json(
            (root / "workflow.json").read_text(encoding="utf-8")
        )
        assert workflow.schema_version == "2b.1"
        assert isinstance(workflow.id, UUID)
        serialised = json.dumps(workflow.model_dump(mode="json")).casefold()
        assert "private limited" not in serialised
        assert "pvt ltd" not in serialised


def test_sales_profile_groups_and_calculates_region_status(tmp_path: Path) -> None:
    _, result = _preview("sales_mis", "input.csv", tmp_path)
    assert result.rows_read == 4
    assert result.rows_written == 2
    assert result.rows_aggregated == 2
    assert [(row["region"], Decimal(str(row["variance"])), row["status"]) for row in result.rows] == [
        ("North", Decimal("5"), "above_target"),
        ("South", Decimal("-20"), "below_target"),
    ]


def test_attendance_invoice_and_inventory_profiles_surface_expected_reasons(
    tmp_path: Path,
) -> None:
    _, attendance = _preview("hr_attendance", "input.csv", tmp_path)
    attendance_reasons = {item.reason_code for item in attendance.findings}
    assert {
        "EMPLOYEE_DATE_DUPLICATE",
        "WORK_DATE_INVALID",
        "ATTENDANCE_STATUS_INVALID",
        "EMPLOYEE_ID_MISSING",
    } <= attendance_reasons

    _, invoice = _preview("invoice_preparation", "input.csv", tmp_path)
    assert invoice.rows[0]["invoice_id"] == "000045"
    assert invoice.rows[0]["ageing_days"] == 16
    assert {item.reason_code for item in invoice.findings} == {"INVOICE_AMOUNT_INVALID"}

    _, inventory = _preview("inventory_movement", "input.xlsx", tmp_path)
    assert inventory.rows[0]["item_id"] == "SKU-001"
    assert str(inventory.rows[0]["calculated_closing"]) == "7"
    assert {item.reason_code for item in inventory.findings} == {"NEGATIVE_STOCK"}


def test_monthly_profile_reuses_one_workflow_after_rename_and_reorder(tmp_path: Path) -> None:
    _, first = _preview("generic_monthly_consolidation", "branch_a.csv", tmp_path)
    _, second = _preview("generic_monthly_consolidation", "branch_b.csv", tmp_path)
    assert first.rows == [
        {"__row_id": 1, "branch_id": "BR-001", "period": "2026-06", "sales": "100"},
        {"__row_id": 2, "branch_id": "BR-002", "period": "2026-06", "sales": "120"},
    ]
    assert second.rows == [
        {"__row_id": 1, "branch_id": "BR-003", "period": "2026-06", "sales": "90"},
        {"__row_id": 2, "branch_id": "BR-004", "period": "2026-06", "sales": "110"},
    ]
    readme = (ROOT / "generic_monthly_consolidation" / "README.md").read_text(encoding="utf-8")
    assert "append remains deferred" in readme
