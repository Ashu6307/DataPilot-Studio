from __future__ import annotations

import pytest

from packages.contracts import WorkflowConfiguration
from packages.workflow_schema import assert_secret_free


def test_sample_workflow_is_portable_and_secret_free(workflow: WorkflowConfiguration) -> None:
    payload = workflow.model_dump(mode="json")
    assert_secret_free(payload)
    text = workflow.model_dump_json()
    assert "tests/fixtures" not in text
    assert "Employee Code" in text  # source labels belong in mappings, never operations
    assert all("Employee Code" not in str(node.config) for node in workflow.operations)


@pytest.mark.parametrize(
    "payload",
    [
        {"password": "plain"},
        {"nested": {"api_key": "plain"}},
        {"value": "sk-example"},
    ],
)
def test_secret_like_configuration_is_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="forbidden"):
        assert_secret_free(payload)

