"""Provider-neutral capability, plugin, and entitlement contracts."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from packages.contracts import OperationMetric, ValidationFinding


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plugin_id: str = Field(pattern=r"^[a-z][a-z0-9.-]+$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    compatibility_version: int = Field(ge=1)
    capabilities: list[str]
    permissions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class Connector(Protocol):
    connector_id: str

    def discover(self, source: Any, config: dict[str, Any]) -> Any: ...

    def read(self, source: Any, config: dict[str, Any]) -> Any: ...


class Processor(Protocol):
    operation_id: str
    operation_version: int

    def apply(self, table: Any, config: dict[str, Any]) -> tuple[Any, OperationMetric]: ...


class Validator(Protocol):
    validator_id: str

    def validate(self, table: Any, config: dict[str, Any]) -> list[ValidationFinding]: ...


class Exporter(Protocol):
    exporter_id: str

    def export(self, payload: Any, destination: Any) -> list[Any]: ...


class EntitlementService(Protocol):
    def is_entitled(self, capability_id: str) -> bool: ...


class AllowAllLocalEntitlements:
    """Development placeholder; not a commercial license implementation."""

    def is_entitled(self, capability_id: str) -> bool:
        return capability_id.startswith("core.")


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[str, dict[str, Any]] = {}

    def register(self, capability_id: str, metadata: dict[str, Any]) -> None:
        if capability_id in self._capabilities:
            raise ValueError(f"duplicate capability: {capability_id}")
        self._capabilities[capability_id] = metadata

    def list(self) -> dict[str, dict[str, Any]]:
        return dict(self._capabilities)

