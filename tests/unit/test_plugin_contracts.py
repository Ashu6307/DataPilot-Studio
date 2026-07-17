from __future__ import annotations

import pytest

from plugins.interfaces import AllowAllLocalEntitlements, CapabilityRegistry, PluginManifest


def test_plugin_manifest_and_registry_are_versioned() -> None:
    manifest = PluginManifest(
        plugin_id="org.datapilot.sample",
        version="1.0.0",
        compatibility_version=1,
        capabilities=["connector.sample"],
    )
    registry = CapabilityRegistry()
    registry.register(manifest.capabilities[0], manifest.model_dump())
    assert "connector.sample" in registry.list()
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(manifest.capabilities[0], {})


def test_placeholder_entitlement_is_provider_neutral() -> None:
    service = AllowAllLocalEntitlements()
    assert service.is_entitled("core.import")
    assert not service.is_entitled("enterprise.sso")

