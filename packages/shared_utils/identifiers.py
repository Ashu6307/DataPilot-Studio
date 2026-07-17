"""Stable identifier helpers."""

from __future__ import annotations

import re
import unicodedata


def slugify_field(label: str, fallback: str = "field") -> str:
    value = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_") or fallback
    if value[0].isdigit():
        value = f"field_{value}"
    return value[:80]
