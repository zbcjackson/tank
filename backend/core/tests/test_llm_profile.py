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

    def test_capabilities_parsed(self):
        profile = resolve_profile("x", {
            "api_key": "k",
            "model": "m",
            "base_url": "http://x",
            "capabilities": ["text", "image"],
        })
        assert profile.capabilities == frozenset({"text", "image"})

    def test_capabilities_default_is_empty(self):
        profile = resolve_profile(
            "x", {"api_key": "k", "model": "m", "base_url": "http://x"}
        )
        assert profile.capabilities == frozenset()

    def test_capabilities_invalid_entry_raises(self):
        with pytest.raises(ValueError, match="unknown capabilities"):
            resolve_profile("x", {
                "api_key": "k",
                "model": "m",
                "base_url": "http://x",
                "capabilities": ["text", "telepathy"],
            })

    def test_capabilities_wrong_shape_raises(self):
        with pytest.raises(ValueError, match="must be a list of strings"):
            resolve_profile("x", {
                "api_key": "k",
                "model": "m",
                "base_url": "http://x",
                "capabilities": "text,image",  # string not list
            })


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
        from tank_backend.config import AppConfig

        app = AppConfig.load(config_file)
        profile = app.get_llm_profile("default")

        assert profile.name == "default"
        assert profile.api_key == "sk-test"
        assert profile.model == "gpt-4"
        assert profile.temperature == 0.3

    def test_missing_default_profile_rejected_at_load(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("llm: {}")

        from tank_backend.config import AppConfig, ConfigError

        with pytest.raises(ConfigError, match="default"):
            AppConfig.load(config_file)

    def test_get_llm_profile_falls_back_to_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_LLM_KEY", "sk-test")
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
llm:
  default:
    api_key: ${TEST_LLM_KEY}
    model: gpt-4
    base_url: https://api.openai.com/v1
""")
        from tank_backend.config import AppConfig

        app = AppConfig.load(config_file)
        profile = app.get_llm_profile("nonexistent")
        assert profile.name == "default"
        assert profile.model == "gpt-4"

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
        from tank_backend.config import AppConfig

        app = AppConfig.load(config_file)
        names = app.list_llm_profiles()

        assert set(names) == {"default", "fast"}


class TestEnvVarInterpolation:
    """Tests for ${VAR} interpolation in AppConfig."""

    # AppConfig.from_raw_dict requires a 'default' LLM profile, so every
    # test in this class includes one in the YAML.
    _DEFAULT_LLM = (
        "llm:\n"
        "  default:\n"
        "    api_key: k\n"
        "    model: m\n"
        "    base_url: u\n"
    )

    def test_interpolation_replaces_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_SECRET", "resolved-value")
        config_file = tmp_path / "config.yaml"
        config_file.write_text(self._DEFAULT_LLM + "key: ${MY_SECRET}")

        from tank_backend.config import AppConfig

        app = AppConfig.load(config_file)
        assert app._raw["key"] == "resolved-value"

    def test_interpolation_raises_on_missing_env_var(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(self._DEFAULT_LLM + "key: ${MISSING_VAR}")

        from tank_backend.config import AppConfig

        with pytest.raises(ValueError, match="MISSING_VAR.*is not set"):
            AppConfig.load(config_file)

    def test_interpolation_multiple_vars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOST", "example.com")
        monkeypatch.setenv("PORT", "8080")
        config_file = tmp_path / "config.yaml"
        config_file.write_text(self._DEFAULT_LLM + "url: http://${HOST}:${PORT}/api")

        from tank_backend.config import AppConfig

        app = AppConfig.load(config_file)
        assert app._raw["url"] == "http://example.com:8080/api"

    def test_no_interpolation_without_dollar_brace(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(self._DEFAULT_LLM + "key: plain_value")

        from tank_backend.config import AppConfig

        app = AppConfig.load(config_file)
        assert app._raw["key"] == "plain_value"

    def test_comments_with_dollar_brace_are_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REAL_KEY", "works")
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            self._DEFAULT_LLM
            + "# Use ${VAR} syntax for env vars\n"
            + "key: ${REAL_KEY}\n",
        )

        from tank_backend.config import AppConfig

        app = AppConfig.load(config_file)
        assert app._raw["key"] == "works"
