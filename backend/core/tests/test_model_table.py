"""Tests for the bundled model registry.

Two classes:

- :class:`TestModelRegistry` exercises lookup logic against
  synthetic yaml fixtures so each test is independent of the real
  bundled snapshot.
- :class:`TestBundledSnapshot` spot-checks the real shipped file for
  a handful of well-known models. These will need updating if/when
  LiteLLM renames them upstream; that's the intended signal.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tank_backend.llm.model_table import (
    ModelRecord,
    ModelRegistry,
    _pick_canonical,
    registry,
    reset_registry_cache,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_yaml(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "models.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Unit tests on synthetic fixtures
# ---------------------------------------------------------------------------


class TestModelRegistry:
    def test_loads_from_yaml(self, tmp_path):
        path = _make_yaml(
            tmp_path,
            """
            models:
              - id: gpt-4o
                provider: openai
                modalities: [text, image, file]
                max_input_tokens: 128000
                max_output_tokens: 16384
                flags: [function_calling]
                costs:
                  input_cost_per_token: 2.5e-06
                  output_cost_per_token: 1e-05
            """,
        )
        reg = ModelRegistry.from_yaml(path)
        assert len(reg) == 1
        rec = reg.lookup("gpt-4o")
        assert rec is not None
        assert rec.id == "gpt-4o"
        assert rec.provider == "openai"
        assert rec.modalities == frozenset({"text", "image", "file"})
        assert rec.max_input_tokens == 128000
        assert rec.max_output_tokens == 16384
        assert rec.flags == frozenset({"function_calling"})
        assert rec.costs["input_cost_per_token"] == pytest.approx(2.5e-06)

    def test_missing_file_returns_empty_registry(self, tmp_path):
        reg = ModelRegistry.from_yaml(tmp_path / "nonexistent.yaml")
        assert len(reg) == 0
        assert reg.lookup("anything") is None

    def test_exact_match_wins(self, tmp_path):
        """When both an exact id and a same-suffix row exist, exact wins."""
        path = _make_yaml(
            tmp_path,
            """
            models:
              - {id: gpt-4o, modalities: [text, image]}
              - {id: azure/gpt-4o, modalities: [text]}
            """,
        )
        reg = ModelRegistry.from_yaml(path)
        rec = reg.lookup("gpt-4o")
        assert rec is not None
        assert rec.id == "gpt-4o"
        assert "image" in rec.modalities

    def test_prefix_strip_falls_through_to_suffix(self, tmp_path):
        """openai/gpt-4o → gpt-4o when no exact match, suffix lookup."""
        path = _make_yaml(
            tmp_path,
            """
            models:
              - {id: gpt-4o, modalities: [text, image]}
            """,
        )
        reg = ModelRegistry.from_yaml(path)
        rec = reg.lookup("openai/gpt-4o")
        assert rec is not None
        assert rec.id == "gpt-4o"

    def test_unprefixed_preferred_over_prefixed(self, tmp_path):
        """If both azure/foo and foo share suffix, unprefixed wins."""
        path = _make_yaml(
            tmp_path,
            """
            models:
              - {id: azure/gpt-4o, modalities: [text]}
              - {id: gpt-4o, modalities: [text, image]}
            """,
        )
        reg = ModelRegistry.from_yaml(path)
        # Looking up a third provider's variant should pick the bare
        # ``gpt-4o`` record, not the azure one.
        rec = reg.lookup("bedrock/gpt-4o")
        assert rec is not None
        assert rec.id == "gpt-4o"

    def test_richer_modality_wins_among_prefixed(self, tmp_path):
        """When only prefixed variants exist, pick the fullest one."""
        path = _make_yaml(
            tmp_path,
            """
            models:
              - {id: azure/gpt-4o, modalities: [text]}
              - {id: vertex_ai/gpt-4o, modalities: [text, image, file]}
              - {id: bedrock/gpt-4o, modalities: [text, image]}
            """,
        )
        reg = ModelRegistry.from_yaml(path)
        # openai/gpt-4o not in the table → suffix match → pick richest.
        rec = reg.lookup("openai/gpt-4o")
        assert rec is not None
        assert rec.id == "vertex_ai/gpt-4o"
        assert len(rec.modalities) == 3

    def test_empty_model_id_returns_none(self, tmp_path):
        path = _make_yaml(tmp_path, "models: []")
        reg = ModelRegistry.from_yaml(path)
        assert reg.lookup("") is None

    def test_unknown_model_returns_none(self, tmp_path):
        path = _make_yaml(
            tmp_path,
            """
            models:
              - {id: gpt-4o, modalities: [text]}
            """,
        )
        reg = ModelRegistry.from_yaml(path)
        assert reg.lookup("never-heard-of-this") is None

    def test_malformed_row_is_skipped(self, tmp_path):
        """A bad entry doesn't kill the whole registry."""
        path = _make_yaml(
            tmp_path,
            """
            models:
              - {id: good-model, modalities: [text]}
              - this-is-not-a-dict
              - {modalities: [text]}  # missing id
              - {id: 123, modalities: [text]}  # non-string id
            """,
        )
        reg = ModelRegistry.from_yaml(path)
        assert len(reg) == 1
        assert reg.lookup("good-model") is not None

    def test_missing_modalities_defaults_to_text(self, tmp_path):
        path = _make_yaml(
            tmp_path,
            """
            models:
              - {id: boring-model}
            """,
        )
        reg = ModelRegistry.from_yaml(path)
        rec = reg.lookup("boring-model")
        assert rec is not None
        assert rec.modalities == frozenset({"text"})

    def test_numeric_coercion_is_defensive(self, tmp_path):
        """Non-int context sizes fall back to None instead of crashing."""
        path = _make_yaml(
            tmp_path,
            """
            models:
              - id: odd-model
                modalities: [text]
                max_input_tokens: "garbage"
                max_output_tokens: 32000
            """,
        )
        reg = ModelRegistry.from_yaml(path)
        rec = reg.lookup("odd-model")
        assert rec is not None
        assert rec.max_input_tokens is None
        assert rec.max_output_tokens == 32000

    def test_costs_non_numeric_dropped(self, tmp_path):
        """String cost values are silently discarded."""
        path = _make_yaml(
            tmp_path,
            """
            models:
              - id: cheap-model
                modalities: [text]
                costs:
                  input_cost_per_token: 0.001
                  output_cost_per_token: "free"
            """,
        )
        reg = ModelRegistry.from_yaml(path)
        rec = reg.lookup("cheap-model")
        assert rec is not None
        assert "input_cost_per_token" in rec.costs
        assert "output_cost_per_token" not in rec.costs

    def test_ids_returns_sorted_list(self, tmp_path):
        path = _make_yaml(
            tmp_path,
            """
            models:
              - {id: zeta, modalities: [text]}
              - {id: alpha, modalities: [text]}
              - {id: mu, modalities: [text]}
            """,
        )
        reg = ModelRegistry.from_yaml(path)
        assert reg.ids() == ["alpha", "mu", "zeta"]


class TestPickCanonical:
    """_pick_canonical isolates the tie-breaking logic."""

    def test_unprefixed_beats_prefixed_with_more_modalities(self):
        # Prefixed has more modalities but unprefixed still wins — the
        # user-configured-direct case is the common one.
        bare = ModelRecord(id="gpt-4o", provider="", modalities=frozenset({"text"}))
        prefixed = ModelRecord(
            id="azure/gpt-4o",
            provider="azure",
            modalities=frozenset({"text", "image", "file"}),
        )
        assert _pick_canonical([prefixed, bare]) is bare

    def test_lexical_tiebreak_among_prefixed(self):
        a = ModelRecord(
            id="azure/gpt-4o", provider="azure",
            modalities=frozenset({"text", "image"}),
        )
        b = ModelRecord(
            id="vertex/gpt-4o", provider="vertex",
            modalities=frozenset({"text", "image"}),
        )
        # Same modality count → lexically larger id wins
        # (deterministic, arbitrary).
        assert _pick_canonical([a, b]) is b


# ---------------------------------------------------------------------------
# Smoke tests against the real bundled snapshot
# ---------------------------------------------------------------------------


class TestBundledSnapshot:
    """Spot-checks of the committed ``data/models.yaml`` snapshot.

    If LiteLLM renames a model upstream (has happened — e.g. Claude
    3.5 vs 3-5), these assertions will fail at CI time, which is the
    right signal to re-run the sync script.
    """

    @pytest.fixture(autouse=True)
    def _reset(self):
        reset_registry_cache()
        yield
        reset_registry_cache()

    def test_registry_not_empty(self):
        reg = registry()
        assert len(reg) > 500  # conservative floor — we expect thousands

    @pytest.mark.parametrize(
        ("model_id", "must_have"),
        [
            ("gpt-4o", {"text", "image"}),
            ("gpt-4o-mini", {"text", "image"}),
            ("gemini-2.5-flash", {"text", "image", "video"}),
        ],
    )
    def test_well_known_models_have_expected_modalities(
        self, model_id, must_have,
    ):
        rec = registry().lookup(model_id)
        assert rec is not None, f"{model_id} missing from snapshot"
        assert must_have.issubset(rec.modalities), (
            f"{model_id} modalities {rec.modalities} missing {must_have}"
        )

    def test_provider_prefixed_lookups_work(self):
        """Users who configure ``openai/gpt-4o`` should resolve cleanly."""
        rec = registry().lookup("openai/gpt-4o")
        assert rec is not None
        assert "image" in rec.modalities

    def test_unknown_model_returns_none(self):
        assert registry().lookup("imaginary-model-xyz-9000") is None
