from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from packages.contracts import WorkflowConfiguration
from scripts.generate_composition_fixtures import main as generate_composition_fixtures
from scripts.generate_fixtures import FIXTURES
from scripts.generate_fixtures import main as generate_fixtures

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def fixtures() -> None:
    generate_fixtures()
    generate_composition_fixtures()


@pytest.fixture
def workflow() -> WorkflowConfiguration:
    payload: dict[str, Any] = json.loads(
        (ROOT / "samples" / "workflows" / "generic_data_quality.json").read_text(encoding="utf-8")
    )
    return WorkflowConfiguration.model_validate(payload)


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURES
