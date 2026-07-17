"""Deterministic key normalisation with original-value audit evidence."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast

from packages.contracts import (
    NormalisationAudit,
    NormalisationOperation,
    NormalisationOperationId,
    NormalisationPipeline,
    NormalisationStepAudit,
)


def _text(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _string_list(parameters: dict[str, Any], key: str) -> list[str]:
    raw = parameters.get(key, [])
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"NORMALISATION_PARAMETER_INVALID:{key}")
    return raw


def apply_operation(value: Any, operation: NormalisationOperation) -> Any:
    """Apply one closed-dispatch operation without mutating source evidence."""

    if not operation.enabled:
        return value
    operation_id = operation.operation_id
    parameters = operation.parameters
    if operation_id == NormalisationOperationId.NULL_LIKE:
        values = _string_list(parameters, "values") or ["", "null", "none", "n/a", "na"]
        if value is None or _text(value).strip().casefold() in {item.casefold() for item in values}:
            return None
        return value
    if value is None:
        return None
    text = _text(value)
    if operation_id == NormalisationOperationId.TRIM_WHITESPACE:
        return text.strip()
    if operation_id == NormalisationOperationId.COLLAPSE_SPACES:
        return re.sub(r"\s+", " ", text).strip()
    if operation_id == NormalisationOperationId.UPPERCASE:
        return text.upper()
    if operation_id == NormalisationOperationId.LOWERCASE:
        return text.lower()
    if operation_id == NormalisationOperationId.REMOVE_PUNCTUATION:
        return "".join(character for character in text if not unicodedata.category(character).startswith("P"))
    if operation_id in {NormalisationOperationId.REMOVE_PREFIXES, NormalisationOperationId.REMOVE_SUFFIXES}:
        key = "prefixes" if operation_id == NormalisationOperationId.REMOVE_PREFIXES else "suffixes"
        candidates = sorted(_string_list(parameters, key), key=len, reverse=True)
        case_sensitive = bool(parameters.get("case_sensitive", False))
        comparable = text if case_sensitive else text.casefold()
        for candidate in candidates:
            expected = candidate if case_sensitive else candidate.casefold()
            if operation_id == NormalisationOperationId.REMOVE_PREFIXES and comparable.startswith(expected):
                return text[len(candidate) :]
            if operation_id == NormalisationOperationId.REMOVE_SUFFIXES and comparable.endswith(expected):
                return text[: -len(candidate)] if candidate else text
        return text
    if operation_id == NormalisationOperationId.REPLACE_DICTIONARY:
        replacements = parameters.get("replacements", {})
        if not isinstance(replacements, dict) or not all(
            isinstance(key, str) and isinstance(replacement, str) for key, replacement in replacements.items()
        ):
            raise ValueError("NORMALISATION_PARAMETER_INVALID:replacements")
        case_sensitive = bool(parameters.get("case_sensitive", False))
        if case_sensitive:
            return replacements.get(text, text)
        lookup = {key.casefold(): replacement for key, replacement in replacements.items()}
        return lookup.get(text.casefold(), text)
    if operation_id == NormalisationOperationId.UNICODE_NORMALISE:
        form = str(parameters.get("form", "NFKC"))
        if form not in {"NFC", "NFD", "NFKC", "NFKD"}:
            raise ValueError("NORMALISATION_PARAMETER_INVALID:form")
        return unicodedata.normalize(cast(Literal["NFC", "NFD", "NFKC", "NFKD"], form), text)
    if operation_id == NormalisationOperationId.NORMALISE_LEADING_ZEROS:
        if not bool(parameters.get("approved", False)):
            raise ValueError("LEADING_ZERO_NORMALISATION_REQUIRES_APPROVAL")
        sign = "-" if text.startswith("-") else ""
        digits = text[1:] if sign else text
        if not digits.isdigit():
            return text
        stripped = digits.lstrip("0") or "0"
        minimum_width = int(parameters.get("minimum_width", 1))
        return sign + stripped.zfill(max(1, minimum_width))
    if operation_id == NormalisationOperationId.REMOVE_SEPARATORS:
        separators = _string_list(parameters, "separators")
        for separator in separators:
            text = text.replace(separator, "")
        return text
    if operation_id == NormalisationOperationId.CANONICAL_DATE:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        formats = _string_list(parameters, "input_formats") or ["%Y-%m-%d"]
        parsed: list[date] = []
        for date_format in formats:
            try:
                parsed.append(datetime.strptime(text.strip(), date_format).date())
            except ValueError:
                continue
        unique = set(parsed)
        if len(unique) != 1:
            raise ValueError("DATE_NORMALISATION_AMBIGUOUS_OR_INVALID")
        return unique.pop().isoformat()
    if operation_id == NormalisationOperationId.CANONICAL_NUMERIC:
        try:
            numeric = Decimal(text.strip())
        except InvalidOperation as error:
            raise ValueError("NUMERIC_NORMALISATION_INVALID") from error
        decimal_places = parameters.get("decimal_places")
        if decimal_places is not None:
            places = int(decimal_places)
            if places < 0 or places > 28:
                raise ValueError("NORMALISATION_PARAMETER_INVALID:decimal_places")
            numeric = numeric.quantize(Decimal(1).scaleb(-places))
        return format(numeric, "f")
    raise ValueError(f"NORMALISATION_OPERATION_UNSUPPORTED:{operation_id}")


def normalise_value(value: Any, pipeline: NormalisationPipeline) -> NormalisationAudit:
    current = value
    steps: list[NormalisationStepAudit] = []
    for operation in pipeline.operations:
        before = current
        current = apply_operation(current, operation)
        changed = current != before or type(current) is not type(before)
        steps.append(
            NormalisationStepAudit(
                operation_id=operation.operation_id,
                operation_version=operation.operation_version,
                input_value=before,
                output_value=current,
                changed=changed,
                reason_code="NORMALISATION_VALUE_CHANGED" if changed else "NORMALISATION_NO_CHANGE",
            )
        )
    return NormalisationAudit(
        pipeline_id=pipeline.id,
        pipeline_version=pipeline.version,
        original_value=value,
        normalised_value=current,
        steps=steps,
    )


def normalise_key(values: list[Any], pipelines: list[NormalisationPipeline | None]) -> tuple[Any, ...]:
    if pipelines and len(values) != len(pipelines):
        raise ValueError("NORMALISATION_KEY_ARITY_MISMATCH")
    if not pipelines:
        return tuple(values)
    return tuple(
        normalise_value(value, pipeline).normalised_value if pipeline is not None else value
        for value, pipeline in zip(values, pipelines, strict=True)
    )
