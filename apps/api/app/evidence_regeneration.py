"""Versioned M2B evidence regeneration from immutable review decisions."""

from __future__ import annotations

from pathlib import Path

from packages.contracts import EvidencePackageVersion, EvidenceRegenerationRequest, ReconciliationResult
from packages.data_engine.reconciliation_exporter import export_reconciliation_evidence
from packages.data_engine.safety import Workspace, sha256_file

from .dag_repository import SQLiteDagRepository
from .repositories import MetadataRepository


class EvidenceRegenerationService:
    def __init__(
        self,
        metadata: MetadataRepository,
        dag_metadata: SQLiteDagRepository,
        workspace: Workspace,
    ) -> None:
        self.metadata = metadata
        self.dag_metadata = dag_metadata
        self.workspace = workspace

    def regenerate(self, request: EvidenceRegenerationRequest) -> EvidencePackageVersion:
        run = self.metadata.get_reconciliation_run(request.run_id)
        if run is None:
            raise KeyError("RECONCILIATION_RUN_NOT_FOUND")
        workflow = self.metadata.get_reconciliation_workflow(run.workflow_id, run.workflow_version)
        if workflow is None:
            raise KeyError("RECONCILIATION_WORKFLOW_VERSION_NOT_FOUND")
        runs_root = self.workspace.runs.resolve()
        result_candidates = [
            Path(value).resolve() for value in run.artifacts if Path(value).name == "reconciliation-result.json"
        ]
        if len(result_candidates) != 1:
            raise FileNotFoundError("RECONCILIATION_RESULT_EVIDENCE_NOT_FOUND")
        result_path = result_candidates[0]
        if runs_root not in result_path.parents or not result_path.is_file():
            raise ValueError("RECONCILIATION_RESULT_PATH_UNSAFE")
        result = ReconciliationResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        # Review status is refreshed from immutable decision events; matching is never rerun.
        result.review_items = self.metadata.list_review_items(request.run_id)
        previous = self.dag_metadata.list_evidence_versions(request.run_id)
        package_version = len(previous) + 1
        output_directory = (runs_root / "evidence-regeneration" / str(request.run_id) / f"v{package_version}").resolve()
        if runs_root not in output_directory.parents:
            raise ValueError("EVIDENCE_OUTPUT_PATH_UNSAFE")
        if output_directory.exists():
            raise FileExistsError("EVIDENCE_PACKAGE_VERSION_EXISTS")
        export_reconciliation_evidence(output_directory, result, workflow, result.integrity_result)
        manifest_path = output_directory / "reconciliation-manifest.json"
        decision_count = sum(len(self.metadata.list_review_decisions(item.id)) for item in result.review_items)
        evidence = EvidencePackageVersion(
            run_id=request.run_id,
            workflow_id=workflow.id,
            workflow_version=workflow.version,
            package_version=package_version,
            review_decision_version=decision_count,
            previous_package_id=previous[-1].id if previous else None,
            manifest_path=str(manifest_path),
            sha256=sha256_file(manifest_path),
            affected_output_node_ids=["reconciliation.evidence_regenerate"],
            reused_checkpoint_node_ids=[stage.id for stage in workflow.stages],
            regenerated_by=request.actor,
        )
        self.dag_metadata.save_evidence_version(evidence)
        return evidence
