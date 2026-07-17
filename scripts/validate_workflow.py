"""Validate a portable workflow without execution."""

from __future__ import annotations

import argparse
from pathlib import Path

from packages.contracts import WorkflowConfiguration
from packages.workflow_schema import assert_secret_free


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workflow", type=Path)
    args = parser.parse_args()
    workflow = WorkflowConfiguration.model_validate_json(args.workflow.read_text(encoding="utf-8"))
    assert_secret_free(workflow.model_dump(mode="json"))
    print(f"Valid workflow {workflow.id} v{workflow.workflow_version}")


if __name__ == "__main__":
    main()

