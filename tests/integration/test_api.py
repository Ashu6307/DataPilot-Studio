from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.app import main
from apps.api.app.database import Database
from apps.api.app.repositories import SQLiteMetadataRepository
from apps.api.app.services import DataPilotService
from packages.contracts import WorkflowConfiguration
from packages.data_engine import Workspace


def test_project_upload_discovery_and_failed_run_history_api(
    fixture_dir: Path,
    tmp_path: Path,
    monkeypatch,
    workflow: WorkflowConfiguration,
) -> None:
    database = Database(tmp_path / "metadata.sqlite3")
    database.initialize()
    repository = SQLiteMetadataRepository(database)
    service = DataPilotService(repository, Workspace(tmp_path / "workspace"))
    monkeypatch.setattr(main, "repository", repository)
    main.app.dependency_overrides[main.get_service] = lambda: service
    try:
        with TestClient(main.app) as client:
            project_response = client.post("/api/v1/projects", json={"name": "Test project"})
            assert project_response.status_code == 201
            project_id = project_response.json()["id"]
            with (fixture_dir / "header_row_1.csv").open("rb") as stream:
                upload = client.post(
                    "/api/v1/sources",
                    data={"project_id": project_id},
                    files={"file": ("header_row_1.csv", stream, "text/csv")},
                )
            assert upload.status_code == 201
            source_id = upload.json()["id"]
            discovery = client.post(
                f"/api/v1/sources/{source_id}/discover",
                json={"header_search_depth": 25, "preview_rows": 10},
            )
            assert discovery.status_code == 200
            assert discovery.json()["tables"][0]["selected_header_row"] == 1
            broken = workflow.model_dump(mode="json")
            broken["project_id"] = project_id
            broken["operations"] = [
                {
                    "id": "50000000-0000-4000-8000-000000000001",
                    "operation_id": "processor.not_installed",
                    "operation_version": 1,
                    "config": {},
                    "enabled": True,
                }
            ]
            failed = client.post(
                "/api/v1/runs",
                json={"source_id": source_id, "workflow": broken},
            )
            assert failed.status_code == 422
            history = client.get(f"/api/v1/runs?project_id={project_id}")
            assert history.status_code == 200
            assert history.json()[0]["status"] == "failed"
    finally:
        main.app.dependency_overrides.clear()
