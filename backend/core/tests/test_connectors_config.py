"""Tests for the ``connectors:`` config section + plugin-type validation."""

from __future__ import annotations

import pytest

from tank_backend.config.app_config import AppConfig
from tank_backend.config.app_config import ConfigError as AppConfigError
from tank_backend.plugin.manager import ConfigError as PluginConfigError
from tank_backend.plugin.manager import validate_connector_refs
from tank_backend.plugin.manifest import ExtensionManifest
from tank_backend.plugin.registry import ExtensionRegistry

# Every AppConfig.from_raw_dict call needs a 'default' LLM profile, since the
# parser validates its presence at startup. Tests merge this into their raw dict.
_LLM_DEFAULT = {"llm": {"default": {"api_key": "k", "model": "m", "base_url": "u"}}}


def _raw(**sections) -> dict:
    return {**_LLM_DEFAULT, **sections}


class TestConnectorsConfigParsing:
    def test_empty_config_has_no_instances(self) -> None:
        cfg = AppConfig.from_raw_dict(_raw())
        assert cfg.connectors.instances == ()

    def test_valid_multi_instance_config(self) -> None:
        cfg = AppConfig.from_raw_dict(_raw(connectors=[
            {
                "instance": "tg",
                "extension": "connector-telegram:connector",
                "config": {"bot_token": "xyz"},
            },
            {
                "instance": "sl",
                "extension": "connector-slack:connector",
                "enabled": False,
            },
        ]))
        assert len(cfg.connectors.instances) == 2
        assert cfg.connectors.instances[0].instance == "tg"
        assert cfg.connectors.instances[0].config == {"bot_token": "xyz"}
        assert cfg.connectors.instances[0].enabled is True
        assert cfg.connectors.instances[1].enabled is False

    def test_duplicate_instance_name_rejected(self) -> None:
        with pytest.raises(AppConfigError, match="duplicate"):
            AppConfig.from_raw_dict(_raw(connectors=[
                {"instance": "dup", "extension": "x:y"},
                {"instance": "dup", "extension": "x:z"},
            ]))

    def test_missing_instance_rejected(self) -> None:
        with pytest.raises(AppConfigError, match="instance"):
            AppConfig.from_raw_dict(_raw(connectors=[{"extension": "x:y"}]))

    def test_missing_extension_rejected(self) -> None:
        with pytest.raises(AppConfigError, match="extension"):
            AppConfig.from_raw_dict(_raw(connectors=[{"instance": "a"}]))

    def test_non_list_top_level_rejected(self) -> None:
        with pytest.raises(AppConfigError, match="list"):
            AppConfig.from_raw_dict(_raw(connectors="not-a-list"))

    def test_non_bool_enabled_rejected(self) -> None:
        with pytest.raises(AppConfigError, match="enabled"):
            AppConfig.from_raw_dict(_raw(connectors=[
                {"instance": "a", "extension": "x:y", "enabled": "yes"},
            ]))

    def test_non_dict_config_rejected(self) -> None:
        with pytest.raises(AppConfigError, match="config"):
            AppConfig.from_raw_dict(_raw(connectors=[
                {"instance": "a", "extension": "x:y", "config": "not-a-dict"},
            ]))


class TestValidateConnectorRefs:
    def _registry_with(
        self, plugin_name: str, ext_name: str, ext_type: str,
    ) -> ExtensionRegistry:
        registry = ExtensionRegistry()
        registry.register(
            plugin_name,
            ExtensionManifest(name=ext_name, type=ext_type, factory="x:y"),
        )
        return registry

    def test_valid_reference_passes(self) -> None:
        registry = self._registry_with(
            "connector-tg", "connector", "connector",
        )
        cfg = AppConfig.from_raw_dict(_raw(connectors=[
            {"instance": "tg", "extension": "connector-tg:connector"},
        ]))
        validate_connector_refs(cfg, registry)  # should not raise

    def test_missing_extension_rejected(self) -> None:
        registry = ExtensionRegistry()
        cfg = AppConfig.from_raw_dict(_raw(connectors=[
            {"instance": "tg", "extension": "missing:connector"},
        ]))
        with pytest.raises(PluginConfigError, match="not registered"):
            validate_connector_refs(cfg, registry)

    def test_wrong_type_rejected(self) -> None:
        registry = self._registry_with(
            "plugin-x", "extension", "tts",  # wrong type
        )
        cfg = AppConfig.from_raw_dict(_raw(connectors=[
            {"instance": "tg", "extension": "plugin-x:extension"},
        ]))
        with pytest.raises(PluginConfigError, match="type 'tts'"):
            validate_connector_refs(cfg, registry)

    def test_disabled_instance_not_validated(self) -> None:
        registry = ExtensionRegistry()  # empty — would fail if validated
        cfg = AppConfig.from_raw_dict(_raw(connectors=[
            {"instance": "off", "extension": "missing:x", "enabled": False},
        ]))
        validate_connector_refs(cfg, registry)  # should not raise

    def test_multiple_errors_collected(self) -> None:
        registry = ExtensionRegistry()
        cfg = AppConfig.from_raw_dict(_raw(connectors=[
            {"instance": "a", "extension": "missing-a:x"},
            {"instance": "b", "extension": "missing-b:y"},
        ]))
        with pytest.raises(PluginConfigError) as exc_info:
            validate_connector_refs(cfg, registry)
        # Both missing references should surface in the single error payload
        assert len(exc_info.value.errors) == 2
