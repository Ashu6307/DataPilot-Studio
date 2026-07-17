"""Portable workflow safety validation."""

from __future__ import annotations

import re
from typing import Any

SECRET_KEY = re.compile(r"(password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key)", re.I)
SECRET_VALUE = re.compile(r"^(?:sk-|Bearer\s+|ghp_|xox[baprs]-)", re.I)


def assert_secret_free(value: Any, path: str = "workflow") -> None:
    """Raise when portable configuration appears to contain secret material."""
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if SECRET_KEY.search(str(key)) and child not in (None, "", "credential_reference"):
                raise ValueError(f"plain-text secret field is forbidden at {child_path}")
            assert_secret_free(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_secret_free(child, f"{path}[{index}]")
    elif isinstance(value, str) and SECRET_VALUE.search(value):
        raise ValueError(f"secret-like value is forbidden at {path}")

