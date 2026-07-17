from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path
from time import monotonic, sleep

from apps.api.app.composition_job_store import SQLiteCompositionJobStore
from apps.api.app.database import Database
from apps.api.app.repositories import SQLiteMetadataRepository
from apps.api.app.services import DataPilotService
from packages.contracts import (
    AppendConfiguration,
    BatchCatalogRequest,
    CanonicalField,
    CanonicalType,
    ColumnMapping,
    CompositionJobSubmission,
    CompositionOperation,
    CompositionPlan,
    CompositionPreviewRequest,
    CompositionRunRequest,
    MappingSet,
    ProjectCreate,
    SchemaAlignmentPlan,
    SourceAlignmentConfiguration,
    SplitConfiguration,
    SplitMode,
)
from packages.data_engine import Workspace
from packages.data_engine.composition_background import LocalCompositionJobExecutor


def _mapping(fields: list[CanonicalField], source_id, columns: dict[str, str]) -> SourceAlignmentConfiguration:  # type: ignore[no-untyped-def]
    return SourceAlignmentConfiguration(
        source_id=source_id,
        mapping=MappingSet(
            canonical_fields=fields,
            mappings=[
                ColumnMapping(
                    source_column=source,
                    canonical_field_id=target,
                    user_confirmed=True,
                )
                for target, source in columns.items()
            ],
        ),
        user_decisions={target: "accept" for target in columns},
    )


def test_two_source_alignment_append_split_and_evidence_are_end_to_end(tmp_path: Path) -> None:
    database = Database(tmp_path / "metadata.sqlite3")
    database.initialize()
    repository = SQLiteMetadataRepository(database)
    workspace = Workspace(tmp_path / "workspace")
    service = DataPilotService(repository, workspace)
    project = service.create_project(ProjectCreate(name="Composition vertical slice"))
    first_bytes = b"Employee ID,Department,Amount\nE-001,Finance,10\nE-002,Sales,20\n"
    second_bytes = b"Amount,Dept,Employee Code,Ignored Extra\n30,Finance,E-003,x\n"
    first = service.import_source(project.id, "first.csv", "text/csv", BytesIO(first_bytes))
    second = service.import_source(project.id, "second.csv", "text/csv", BytesIO(second_bytes))
    catalog = service.batch_catalog(BatchCatalogRequest(project_id=project.id, source_ids=[first.id, second.id]))
    assert catalog.files_eligible == 2
    fields = [
        CanonicalField(id="employee_id", label="Employee ID", required=True),
        CanonicalField(id="department", label="Department", required=True),
        CanonicalField(id="amount", label="Amount", data_type=CanonicalType.DECIMAL, required=True),
    ]
    plan = CompositionPlan(
        project_id=project.id,
        display_name="Aligned departmental append",
        source_ids=[first.id, second.id],
        alignment=SchemaAlignmentPlan(
            canonical_fields=fields,
            sources=[
                _mapping(
                    fields,
                    first.id,
                    {"employee_id": "Employee ID", "department": "Department", "amount": "Amount"},
                ),
                _mapping(
                    fields,
                    second.id,
                    {"employee_id": "Employee Code", "department": "Dept", "amount": "Amount"},
                ),
            ],
        ),
        operation=CompositionOperation.APPEND,
        append=AppendConfiguration(output_field_order=["employee_id", "department", "amount"]),
        split=SplitConfiguration(fields=["department"], mode=SplitMode.CSV_FILES),
    )
    service.save_composition_plan(plan)
    preview = service.preview_composition(CompositionPreviewRequest(plan=plan, row_limit=10))
    assert preview.input_rows == 3
    assert preview.output_rows == 3
    assert {row["employee_id"] for row in preview.rows} == {"E-001", "E-002", "E-003"}

    sources = {source_id: service._source(source_id) for source_id in plan.source_ids}
    source_fingerprints = {source_id: source.sha256 for source_id, (_, source) in sources.items()}
    store = SQLiteCompositionJobStore(database)
    executor = LocalCompositionJobExecutor(store, service.run_composition_background)
    try:
        job = executor.submit(CompositionJobSubmission(run=CompositionRunRequest(plan=plan)))
        deadline = monotonic() + 10
        while monotonic() < deadline:
            current = store.get(job.id)
            assert current is not None
            if current.status in {"succeeded", "partial", "failed", "cancelled"}:
                break
            sleep(0.01)
        assert current.status == "succeeded"
        assert current.run_id is not None
        record = repository.get_run(current.run_id)
        manifest = repository.get_batch_manifest(current.run_id)
        assert record is not None and manifest is not None
        assert len(store.checkpoints(job.id)) == 2
    finally:
        executor.shutdown()

    assert manifest.rows_read == 3
    assert manifest.rows_output == 3
    assert sum(manifest.source_row_counts.values()) == 3
    assert (
        manifest.rows_output + manifest.rows_rejected + manifest.rows_review + manifest.rows_filtered
        == manifest.rows_read
    )
    assert sum(entry.rows for entry in manifest.outputs if entry.relative_path.startswith("splits/")) == 3
    assert repository.get_batch_manifest(record.id) == manifest
    output_names = {entry.relative_path for entry in manifest.outputs}
    assert "processed-output.csv" in output_names
    assert "rejected-files.json" in output_names
    evidence = next(path for path in record.artifacts if path.endswith(".zip") and "batch-evidence" in path)
    with zipfile.ZipFile(evidence) as bundle:
        bundled_names = bundle.namelist()
    assert "first.csv" not in bundled_names and "second.csv" not in bundled_names
    for source_id, (_, source) in sources.items():
        source.assert_unchanged()
        assert source.sha256 == source_fingerprints[source_id]
    with database.connect() as connection:
        decision_count = connection.execute(
            "SELECT COUNT(*) FROM alignment_decisions WHERE plan_id = ?",
            (str(plan.id),),
        ).fetchone()[0]
    assert decision_count == 2
