from __future__ import annotations

import json
from pathlib import Path

from packages.contracts import DagWorkflow
from packages.workflow_dag import build_execution_plan, validate_dag


def test_all_visual_workflow_templates_are_documented_valid_and_plannable() -> None:
    root = Path("samples/dag_templates")
    directories = sorted(path for path in root.iterdir() if path.is_dir())
    assert len(directories) == 5
    for directory in directories:
        workflow = DagWorkflow.model_validate_json((directory / "workflow.json").read_text(encoding="utf-8"))
        parameters = json.loads((directory / "sample-parameters.json").read_text(encoding="utf-8"))
        assert parameters
        assert (directory / "input.csv").is_file()
        assert "Expected execution path" in (directory / "README.md").read_text(encoding="utf-8")
        validation = validate_dag(workflow)
        assert validation.valid, [(item.reason_code, item.explanation) for item in validation.findings]
        plan = build_execution_plan(workflow)
        assert plan.nodes
        assert plan.plan_fingerprint
