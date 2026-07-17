"""Typed runtime parameter resolution with secret-safe audit output."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from packages.contracts import (
    DagLimits,
    ParameterType,
    RuntimeOverridePolicy,
    RuntimeParameterDefinition,
    RuntimeParameterValue,
)

PARAMETER_REFERENCE = re.compile(r"^\$\{parameters\.([a-z][a-z0-9_]*)\}$")


def referenced_parameter_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for child in value.values():
            found.update(referenced_parameter_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(referenced_parameter_ids(child))
    elif isinstance(value, str):
        match = PARAMETER_REFERENCE.fullmatch(value)
        if match:
            found.add(match.group(1))
    return found


def _coerce(value: Any, definition: RuntimeParameterDefinition) -> Any:
    kind = definition.data_type
    if value is None:
        return None
    if kind in {
        ParameterType.TEXT,
        ParameterType.FILE_REFERENCE,
        ParameterType.FOLDER_REFERENCE,
        ParameterType.CHOICE,
        ParameterType.CANONICAL_FIELD,
        ParameterType.CREDENTIAL_REFERENCE,
    }:
        parsed: Any = str(value)
    elif kind == ParameterType.INTEGER:
        if isinstance(value, bool):
            raise ValueError("boolean is not an integer parameter")
        parsed = int(value)
    elif kind == ParameterType.DECIMAL:
        try:
            parsed = Decimal(str(value))
        except InvalidOperation as error:
            raise ValueError("invalid decimal parameter") from error
    elif kind == ParameterType.BOOLEAN:
        if isinstance(value, bool):
            parsed = value
        elif str(value).casefold() in {"true", "1", "yes"}:
            parsed = True
        elif str(value).casefold() in {"false", "0", "no"}:
            parsed = False
        else:
            raise ValueError("invalid boolean parameter")
    elif kind == ParameterType.DATE:
        parsed = (
            value if isinstance(value, date) and not isinstance(value, datetime) else date.fromisoformat(str(value))
        )
    elif kind == ParameterType.DATETIME:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    elif kind == ParameterType.MULTI_CHOICE:
        if not isinstance(value, list):
            raise ValueError("multi-choice parameter must be a list")
        parsed = [str(item) for item in value]
    else:
        raise ValueError(f"unsupported parameter type: {kind}")
    if definition.allowed_values:
        values = parsed if isinstance(parsed, list) else [parsed]
        if any(item not in definition.allowed_values for item in values):
            raise ValueError("parameter value is not in allowed_values")
    validation = definition.validation
    if isinstance(parsed, (int, Decimal)) and not isinstance(parsed, bool):
        numeric = Decimal(str(parsed))
        if validation.minimum is not None and numeric < validation.minimum:
            raise ValueError("parameter is below configured minimum")
        if validation.maximum is not None and numeric > validation.maximum:
            raise ValueError("parameter exceeds configured maximum")
    if isinstance(parsed, str):
        if validation.minimum_length is not None and len(parsed) < validation.minimum_length:
            raise ValueError("parameter is shorter than configured minimum")
        if validation.maximum_length is not None and len(parsed) > validation.maximum_length:
            raise ValueError("parameter exceeds configured maximum length")
        if validation.pattern and re.fullmatch(validation.pattern, parsed) is None:
            raise ValueError("parameter does not match configured pattern")
        if kind == ParameterType.CREDENTIAL_REFERENCE and not parsed.startswith("credential://"):
            raise ValueError("credential values must be opaque credential:// references")
        if kind in {ParameterType.FILE_REFERENCE, ParameterType.FOLDER_REFERENCE} and ".." in parsed.replace(
            "\\", "/"
        ).split("/"):
            raise ValueError("parameter path reference may not traverse parent directories")
    return parsed


def resolve_runtime_parameters(
    definitions: list[RuntimeParameterDefinition],
    overrides: list[RuntimeParameterValue],
    limits: DagLimits,
) -> tuple[dict[str, Any], dict[str, Any]]:
    definition_ids = [item.id for item in definitions]
    if len(definition_ids) != len(set(definition_ids)):
        raise ValueError("DAG_PARAMETER_ID_DUPLICATE")
    override_map = {item.parameter_id: item.value for item in overrides}
    if len(override_map) != len(overrides):
        raise ValueError("DAG_PARAMETER_OVERRIDE_DUPLICATE")
    unknown = set(override_map) - set(definition_ids)
    if unknown:
        raise ValueError(f"DAG_PARAMETER_UNKNOWN:{sorted(unknown)}")
    resolved: dict[str, Any] = {}
    audit: dict[str, Any] = {}
    for definition in definitions:
        overridden = definition.id in override_map
        if overridden and definition.override_policy == RuntimeOverridePolicy.FORBID:
            raise ValueError(f"DAG_PARAMETER_OVERRIDE_FORBIDDEN:{definition.id}")
        if definition.override_policy == RuntimeOverridePolicy.REQUIRE and not overridden:
            raise ValueError(f"DAG_PARAMETER_OVERRIDE_REQUIRED:{definition.id}")
        raw = override_map.get(definition.id, definition.default_value)
        if raw is None and definition.required:
            raise ValueError(f"DAG_PARAMETER_REQUIRED:{definition.id}")
        parsed = _coerce(raw, definition)
        resolved[definition.id] = parsed
        audit[definition.id] = "[SENSITIVE_REFERENCE]" if definition.secret else parsed
    payload_size = len(json.dumps(resolved, default=str).encode("utf-8"))
    if payload_size > limits.maximum_parameter_bytes:
        raise ValueError("DAG_PARAMETER_PAYLOAD_LIMIT_EXCEEDED")
    return resolved, audit


def substitute_parameters(value: Any, resolved: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: substitute_parameters(child, resolved) for key, child in value.items()}
    if isinstance(value, list):
        return [substitute_parameters(child, resolved) for child in value]
    if isinstance(value, str):
        match = PARAMETER_REFERENCE.fullmatch(value)
        if match:
            return resolved[match.group(1)]
    return value
