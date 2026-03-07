"""Tests for LLM profile system."""

import pytest

from tank_backend.llm.profile import LLMProfile, create_llm_from_profile, resolve_profile


class TestResolveProfile:
    """Tests for resolve_profile()."""

    def test_success(self):
        raw = {
            "api_key": "sk-test-123",
            "model": "gpt-4",
            "base_url": "https://api.openai.com/v1",
            "temperature": 0.5,
            "max_tokens": 2000,
            "extra_headers": {"X-Custom": "value"},
            "stream_options": False,
        }
        profile = resolve_profile("test", raw)

        assert profile.name == "test"
        assert profile.api_key == "sk-test-123"
        assert profile.model == "gpt-4"
        assert profile.base_url == "https://api.openai.com/v1"
        assert profile.temperature == 0.5
        assert profile.max_tokens == 2000
        assert profile.extra_headers == {"X-Custom": "value"}
        assert profile.stream_options is False

    def test_defaults(self):
        raw = {
            "api_key": "secret",
            "model": "claude-3",
            "base_url": "https://example.com/v1",
        }
        profile = resolve_profile("default", raw)

        assert profile.temperature == 0.7
        assert profile.max_tokens == 10000
        assert profile.extra_headers == {}
        assert profile.stream_options is True

    def test_missing_api_key(self):
        with pytest.raises(ValueError, match="missing or empty 'api_key'"):
            resolve_profile("bad", {"model": "x", "base_url": "http://x"})

    def test_empty_api_key(self):
        with pytest.raises(ValueError, match="missing or empty 'api_key'"):
            resolve_profile("bad", {"api_key": "", "model": "x", "base_url": "http://x"})

    def test_missing_model(self):
        with pytest.raises(ValueError, match="missing 'model'"):
            resolve_profile("bad", {"api_key": "k", "base_url": "http://x"})

    def test_missing_base_url(self):
        with pytest.raises(ValueError, match="missing 'base_url'"):
            resolve_profile("bad", {"api_key": "k", "model": "x"})

    def test_frozen(self):
        profile = resolve_profile(
            "x", {"api_key": "k", "model": "m", "base_url": "http://x"}
        )
        with pytest.raises(AttributeError):
            profile.model = "changed"


class TestCreateLlmFromProfile:
    """Tests for create_llm_from_profile()."""

    def test_creates_llm_with_correct_args(self):
        profile = LLMProfile(
            name="test",
            api_key="sk-abc",
            model="gpt-4",
            base_url="https://api.openai.com/v1",
            extra_headers={"X-Title": "Tank"},
            stream_options=False,
        )
        llm = create_llm_from_profile(profile)

        assert llm.model == "gpt-4"
        assert llm.base_url == "https://api.openai.com/v1"
        assert llm.api_key == "sk-abc"
        assert llm.stream_options is False

    def test_creates_llm_without_extra_headers(self):
        profile = LLMProfile(
            name="minimal",
            api_key="sk-xyz",
            model="claude-3",
            base_url="https://example.com/v1",
        )
        llm = create_llm_from_profile(profile)
        assert llm.model == "claude-3"


class TestAppConfigLlmProfiles:
    """Tests for AppConfig.get_llm_profile / list_llm_profiles."""

    def test_get_llm_profile(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_LLM_KEY", "sk-test")
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
llm:
  default:
    api_key: ${TEST_LLM_KEY}
    model: gpt-4
    base_url: https://api.openai.com/v1
    temperature: 0.3
""")
        from tank_backend.plugin.config import AppConfig

        app = AppConfig(config_file)
        profile = app.get_llm_profile("default")

        assert profile.name == "default"
        assert profile.api_key == "sk-test"
        assert profile.model == "gpt-4"
        assert profile.temperature == 0.3

    def test_get_llm_profile_not_found(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("llm: {}")

        from tank_backend.plugin.config import AppConfig

        app = AppConfig(config_file)
        with pytest.raises(ValueError, match="not found"):
            app.get_llm_profile("nonexistent")

    def test_list_llm_profiles(self, tmp_path, monkeypatch):
        monkeypatch.setenv("K1", "v1")
        monkeypatch.setenv("K2", "v2")
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
llm:
  default:
    api_key: ${K1}
    model: m1
    base_url: http://a
  fast:
    api_key: ${K2}
    model: m2
    base_url: http://b
""")
        from tank_backend.plugin.config import AppConfig

        app = AppConfig(config_file)
        names = app.list_llm_profiles()

        assert set(names) == {"default", "fast"}


class TestEnvVarInterpolation:
    """Tests for ${VAR} interpolation in AppConfig."""

    def test_interpolation_replaces_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_SECRET", "resolved-value")
        config_file = tmp_path / "config.yaml"
        config_file.write_text("key: ${MY_SECRET}")

        from tank_backend.plugin.config import AppConfig

        app = AppConfig(config_file)
        assert app._config["key"] == "resolved-value"

    def test_interpolation_raises_on_missing_env_var(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        config_file = tmp_path / "config.yaml"
        config_file.write_text("key: ${MISSING_VAR}")

        from tank_backend.plugin.config import AppConfig

        with pytest.raises(ValueError, match="MISSING_VAR.*is not set"):
            AppConfig(config_file)

    def test_interpolation_multiple_vars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOST", "example.com")
        monkeypatch.setenv("PORT", "8080")
        config_file = tmp_path / "config.yaml"
        config_file.write_text("url: http://${HOST}:${PORT}/api")

        from tank_backend.plugin.config import AppConfig

        app = AppConfig(config_file)
        assert app._config["url"] == "http://example.com:8080/api"

    def test_no_interpolation_without_dollar_brace(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("key: plain_value")

        from tank_backend.plugin.config import AppConfig

        app = AppConfig(config_file)
        assert app._config["key"] == "plain_value"

    def test_comments_with_dollar_brace_are_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REAL_KEY", "works")
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "# Use ${VAR} syntax for env vars\n"
            "key: ${REAL_KEY}\n"
        )

        from tank_backend.plugin.config import AppConfig

        app = AppConfig(config_file)
        assert app._config["key"] == "works"
