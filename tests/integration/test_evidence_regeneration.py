from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from apps.api.app.dag_repository import SQLiteDagRepository
from apps.api.app.database import Database
from apps.api.app.evidence_regeneration import EvidenceRegenerationService
from apps.api.app.repositories import SQLiteMetadataRepository
from packages.contracts import (
    EvidenceRegenerationRequest,
    ReconciliationResult,
    ReconciliationRunRecord,
    ReviewDecision,
    ReviewDecisionEvent,
)
from packages.data_engine.reconciliation_exporter import export_reconciliation_evidence
from packages.data_engine.safety import Workspace
from scripts.benchmark_m2b import fuzzy_and_review


def test_review_aware_evidence_regeneration_versions_outputs_without_rematching(tmp_path: Path) -> None:
    database = Database(tmp_path / "metadata.sqlite3")
    database.initialize()
    metadata = SQLiteMetadataRepository(database)
    dag_metadata = SQLiteDagRepository(database)
    workspace = Workspace(tmp_path / "workspace")
    _, (workflow, result) = fuzzy_and_review(3)
    now = datetime.now(UTC).isoformat()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?)",
            (str(workflow.project_id), "Evidence test", "en-IN", "local_only", now, now),
        )
    metadata.save_reconciliation_workflow(workflow)
    original_directory = workspace.runs / "original" / "outputs"
    export_reconciliation_evidence(original_directory, result, workflow)
    artifacts = [str(path) for path in original_directory.rglob("*") if path.is_file()]
    metadata.save_reconciliation_run(
        ReconciliationRunRecord(
            run_id=result.run_id,
            project_id=workflow.project_id,
            workflow_id=workflow.id,
            workflow_version=workflow.version,
            status=result.status,
            summary=result.summary,
            audit=result.audit,
            artifacts=artifacts,
        )
    )
    metadata.save_review_items(result.review_items)
    review = result.review_items[0]
    metadata.append_review_decision(
        ReviewDecisionEvent(
            review_item_id=review.id,
            decision=ReviewDecision.REJECT_ALL,
            reviewer="evidence-reviewer",
            comment="Candidates do not represent the same record.",
        )
    )
    service = EvidenceRegenerationService(metadata, dag_metadata, workspace)
    first = service.regenerate(EvidenceRegenerationRequest(run_id=result.run_id, actor="evidence-reviewer"))
    second = service.regenerate(EvidenceRegenerationRequest(run_id=result.run_id, actor="evidence-reviewer"))

    assert first.package_version == 1
    assert first.review_decision_version == 1
    assert second.package_version == 2
    assert second.previous_package_id == first.id
    assert first.manifest_path != second.manifest_path
    regenerated_result_path = Path(first.manifest_path).parent / "reconciliation-result.json"
    regenerated = ReconciliationResult.model_validate_json(regenerated_result_path.read_text(encoding="utf-8"))
    assert regenerated.matches == result.matches
    assert regenerated.review_items[0].status.value == "rejected"
