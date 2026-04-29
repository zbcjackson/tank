"""Tests for typed config models, parse_section helper, and AppConfig."""

from __future__ import annotations

import textwrap

import pytest

from tank_backend.config.app_config import AppConfig, ConfigError
from tank_backend.config.models import (
    AgentsConfig,
    BrainConfig,
    EchoGuardConfig,
    JobsConfig,
    MemoryConfig,
    NetworkAccessConfig,
    SkillsConfig,
)
from tank_backend.config.parser import parse_section


class TestParseSection:
    """parse_section converts raw dicts to frozen dataclasses."""

    def test_empty_dict_returns_defaults(self):
        result = parse_section(BrainConfig, {})
        assert result == BrainConfig()
        assert result.max_history_tokens == 8000

    def test_valid_dict_overrides_defaults(self):
        result = parse_section(BrainConfig, {"max_history_tokens": 16000})
        assert result.max_history_tokens == 16000

    def test_unknown_keys_are_ignored(self):
        result = parse_section(BrainConfig, {
            "max_history_tokens": 4000,
            "future_key": "ignored",
        })
        assert result.max_history_tokens == 4000

    def test_none_input_returns_defaults(self):
        result = parse_section(BrainConfig, None)
        assert result == BrainConfig()

    def test_wrong_type_raises_config_error(self):
        with pytest.raises(ConfigError, match="max_history_tokens"):
            parse_section(BrainConfig, {"max_history_tokens": "not_a_number"})

    def test_result_is_frozen(self):
        result = parse_section(BrainConfig, {})
        with pytest.raises(AttributeError):
            result.max_history_tokens = 999

    def test_int_accepted_for_float_field(self):
        result = parse_section(EchoGuardConfig, {"vad_threshold_during_playback": 1})
        assert result.vad_threshold_during_playback == 1.0

    def test_list_field_accepts_list(self):
        result = parse_section(NetworkAccessConfig, {"rules": [{"hosts": ["x.com"]}]})
        assert len(result.rules) == 1

    def test_list_field_rejects_non_list(self):
        with pytest.raises(ConfigError, match="rules"):
            parse_section(NetworkAccessConfig, {"rules": "not_a_list"})


class TestEchoGuardConfig:
    """EchoGuardConfig flattens the nested self_echo_detection sub-dict."""

    def test_defaults(self):
        cfg = parse_section(EchoGuardConfig, {})
        assert cfg.enabled is True
        assert cfg.similarity_threshold == 0.6
        assert cfg.window_seconds == 10.0

    def test_from_yaml_structure(self):
        """config.yaml has self_echo_detection as a nested dict."""
        raw = {
            "enabled": True,
            "vad_threshold_during_playback": 0.9,
            "self_echo_detection": {
                "similarity_threshold": 0.8,
                "window_seconds": 5.0,
            },
        }
        cfg = parse_section(EchoGuardConfig, raw)
        assert cfg.vad_threshold_during_playback == 0.9
        assert cfg.similarity_threshold == 0.8
        assert cfg.window_seconds == 5.0

    def test_disabled(self):
        cfg = parse_section(EchoGuardConfig, {"enabled": False})
        assert cfg.enabled is False


class TestJobsConfig:
    def test_defaults_disabled(self):
        cfg = parse_section(JobsConfig, {})
        assert cfg.enabled is False

    def test_enabled_with_overrides(self):
        cfg = parse_section(JobsConfig, {
            "enabled": True,
            "max_parallel": 5,
            "tick_interval": 30,
        })
        assert cfg.enabled is True
        assert cfg.max_parallel == 5
        assert cfg.tick_interval == 30


class TestAgentsConfig:
    def test_defaults(self):
        cfg = parse_section(AgentsConfig, {})
        assert cfg.llm_profile == "default"
        assert cfg.max_depth == 3

    def test_custom_dirs(self):
        cfg = parse_section(AgentsConfig, {"dirs": ["/custom/agents"]})
        assert cfg.dirs == ["/custom/agents"]


class TestMemoryConfig:
    def test_defaults_disabled(self):
        cfg = parse_section(MemoryConfig, {})
        assert cfg.enabled is False

    def test_enabled_with_db_path(self):
        cfg = parse_section(MemoryConfig, {"enabled": True, "db_path": "/data/mem"})
        assert cfg.enabled is True
        assert cfg.db_path == "/data/mem"


class TestSkillsConfig:
    def test_defaults(self):
        cfg = parse_section(SkillsConfig, {})
        assert cfg.enabled is True
        assert cfg.auto_approve_threshold == "low"


class TestAppConfig:
    """AppConfig.from_raw_dict parses all sections into typed fields."""

    MINIMAL_RAW = {
        "llm": {
            "default": {
                "api_key": "test-key",
                "model": "gpt-4",
                "base_url": "https://api.example.com/v1",
            },
        },
    }

    def test_minimal_config_uses_defaults_for_all_sections(self):
        cfg = AppConfig.from_raw_dict(self.MINIMAL_RAW)
        assert cfg.brain == BrainConfig()
        assert cfg.echo_guard == EchoGuardConfig()
        assert cfg.jobs == JobsConfig()
        assert cfg.agents == AgentsConfig()
        assert cfg.memory == MemoryConfig()

    def test_llm_profiles_parsed(self):
        cfg = AppConfig.from_raw_dict(self.MINIMAL_RAW)
        profile = cfg.get_llm_profile("default")
        assert profile.model == "gpt-4"
        assert profile.api_key == "test-key"

    def test_missing_default_llm_profile_raises_on_access(self):
        raw = {"llm": {"custom": {"api_key": "k", "model": "m", "base_url": "u"}}}
        cfg = AppConfig.from_raw_dict(raw)
        with pytest.raises(ConfigError, match="default"):
            cfg.get_llm_profile("default")

    def test_unknown_llm_profile_raises(self):
        cfg = AppConfig.from_raw_dict(self.MINIMAL_RAW)
        with pytest.raises(ConfigError, match="nonexistent"):
            cfg.get_llm_profile("nonexistent")

    def test_brain_section_parsed(self):
        raw = {**self.MINIMAL_RAW, "brain": {"max_history_tokens": 32000}}
        cfg = AppConfig.from_raw_dict(raw)
        assert cfg.brain.max_history_tokens == 32000

    def test_echo_guard_nested_structure_parsed(self):
        raw = {
            **self.MINIMAL_RAW,
            "echo_guard": {
                "vad_threshold_during_playback": 0.9,
                "self_echo_detection": {
                    "similarity_threshold": 0.8,
                },
            },
        }
        cfg = AppConfig.from_raw_dict(raw)
        assert cfg.echo_guard.vad_threshold_during_playback == 0.9
        assert cfg.echo_guard.similarity_threshold == 0.8

    def test_jobs_section_parsed(self):
        raw = {**self.MINIMAL_RAW, "jobs": {"enabled": True, "max_parallel": 5}}
        cfg = AppConfig.from_raw_dict(raw)
        assert cfg.jobs.enabled is True
        assert cfg.jobs.max_parallel == 5

    def test_invalid_type_raises_config_error(self):
        raw = {**self.MINIMAL_RAW, "brain": {"max_history_tokens": "big"}}
        with pytest.raises(ConfigError, match="max_history_tokens"):
            AppConfig.from_raw_dict(raw)

    def test_config_is_frozen(self):
        cfg = AppConfig.from_raw_dict(self.MINIMAL_RAW)
        with pytest.raises(AttributeError):
            cfg.brain = BrainConfig(max_history_tokens=1)

    def test_load_from_yaml_file(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            llm:
              default:
                api_key: file-key
                model: gpt-4
                base_url: https://api.example.com/v1
            brain:
              max_history_tokens: 64000
        """)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_content)
        cfg = AppConfig.load(config_file)
        assert cfg.brain.max_history_tokens == 64000
        assert cfg.get_llm_profile("default").api_key == "file-key"

    def test_feature_configs_accessible(self):
        raw = {
            **self.MINIMAL_RAW,
            "asr": {"enabled": True, "extension": "asr-funasr:asr", "config": {"model": "x"}},
        }
        cfg = AppConfig.from_raw_dict(raw)
        assert cfg.asr.enabled is True
        assert cfg.asr.extension == "asr-funasr:asr"

    def test_get_section_backward_compat(self):
        raw = {**self.MINIMAL_RAW, "brain": {"max_history_tokens": 16000}}
        cfg = AppConfig.from_raw_dict(raw)
        section = cfg.get_section("brain", {"max_history_tokens": 8000})
        assert section["max_history_tokens"] == 16000
