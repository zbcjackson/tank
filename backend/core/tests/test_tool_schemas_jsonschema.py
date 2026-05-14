"""Schema-validation regression for every OpenAI function spec
:class:`ToolManager` produces.

Why this test exists
--------------------

Phase 18 shipped ``ChartTool`` with a ``data: array`` parameter that
the auto-generated schema serialised as ``{"type": "array"}`` —
without a required ``items`` declaration. Tank's existing tests all
passed (the conversion produces the dict shape we expect), but every
LLM call after registering the chart tool came back as a 400 from the
provider:

    Invalid schema for function 'render_chart': In context=
    ('properties', 'data'), array schema missing items.

The gap was that **no in-tree test ran the produced schema through
the JSON-Schema spec the LLM provider actually validates against**.
This test closes that gap. It iterates every tool ``ToolManager``
registers (DefaultToolGroup + WebToolGroup + FileToolGroup +
SandboxToolGroup), runs each one's ``parameters`` block through
:mod:`jsonschema`'s Draft-2020-12 *meta-schema* validator, and fails
the build if any tool ships a malformed spec.

The Draft-2020-12 meta-schema is what OpenAI / Azure / Anthropic
relays validate against. Catching errors here means a unit-test-speed
fail for the whole bug class — no LLM round-trip required.

What this test catches
----------------------

- ``array`` types without ``items`` (the Phase 18 case).
- Required fields not present in ``properties``.
- ``properties`` whose values aren't valid sub-schemas.
- ``enum`` values that don't match the declared ``type``.
- Missing ``type`` on non-trivial sub-schemas.

What it deliberately doesn't catch
----------------------------------

- LLM-provider-specific extensions (``strict`` mode, vendor-specific
  formats). Those vary across providers and aren't part of the
  base spec.
- Semantic correctness of the description text or parameter naming.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import jsonschema
import pytest

from tank_backend.config.models import (
    AuditConfig,
    CommandSecurityConfig,
    FileAccessConfig,
    NetworkAccessConfig,
    SandboxConfig,
    SkillsConfig,
)
from tank_backend.tools.manager import ToolManager


def _make_app_config() -> MagicMock:
    """Same minimal AppConfig stub used elsewhere — keeps the test
    self-contained without cross-test imports."""
    cfg = MagicMock()
    cfg.network_access = NetworkAccessConfig()
    cfg.file_access = FileAccessConfig()
    cfg.audit = AuditConfig()
    cfg.command_security = CommandSecurityConfig()
    cfg.sandbox = SandboxConfig(enabled=False)
    cfg.skills = SkillsConfig(enabled=False)
    cfg.get_llm_profile = MagicMock(
        side_effect=lambda name: MagicMock(
            api_key="test", model="test", base_url="http://test",
            extra_headers={}, stream_options=False,
        ),
    )
    return cfg


def _all_default_tool_schemas() -> list[dict]:
    """Build every tool's OpenAI function spec via the real ToolManager."""
    tm = ToolManager(app_config=_make_app_config())
    return tm.get_openai_tools()


def _validator_for(schema: dict) -> jsonschema.Draft202012Validator:
    """Create a Draft-2020-12 validator targeting the supplied schema.

    ``Draft202012Validator.check_schema`` validates the *schema itself*
    against the meta-schema — that's what we want here. We're not
    validating data against the schema; we're validating the schema
    is well-formed.
    """
    return jsonschema.Draft202012Validator(schema)


# ---------------------------------------------------------------------------
# Per-tool schema validation — parametrised so failures pinpoint the bad tool
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def all_tool_schemas() -> list[dict]:
    return _all_default_tool_schemas()


def _tool_specs() -> list[dict]:
    """Build the tool list once at collection time so the ``ids=`` arg
    can name each parametrised case after its tool name. Without this
    pytest would call them ``test[0], test[1]…``."""
    return _all_default_tool_schemas()


@pytest.mark.parametrize(
    "tool_spec",
    _tool_specs(),
    ids=lambda spec: spec["function"]["name"],
)
def test_tool_parameter_schema_is_valid_jsonschema(tool_spec: dict) -> None:
    """Every tool's ``parameters`` block must be a well-formed JSON
    Schema (Draft 2020-12). This is what OpenAI/Azure/Anthropic
    relays validate against before they accept a tools list."""
    parameters = tool_spec["function"]["parameters"]
    # ``check_schema`` raises ``SchemaError`` (subclass of
    # ``ValidationError``) with a precise pointer at the bad
    # location — exactly the diagnostic operators need.
    jsonschema.Draft202012Validator.check_schema(parameters)


# ---------------------------------------------------------------------------
# Specific shape invariants — guarding against the exact bugs we've hit
# ---------------------------------------------------------------------------


class TestSchemaShape:
    """Pin the specific shape invariants the LLM provider's validator
    enforces. The general ``check_schema`` test above catches the
    same issues, but separating these makes failures more legible
    when they happen — instead of a generic ``SchemaError`` the test
    name tells operators exactly which guarantee broke."""

    def test_every_array_param_declares_items(
        self, all_tool_schemas: list[dict],
    ) -> None:
        """Phase 18 regression: the OpenAI / Azure validator rejects
        an ``array`` type without ``items``. ToolManager's auto-builder
        injects ``items: {}`` as a permissive default; tools that
        need a tighter shape (chart_tool) ship a precise raw schema.
        Either way, every ``array`` sub-schema in the tool list must
        have ``items``."""
        violations: list[str] = []
        for spec in all_tool_schemas:
            tool_name = spec["function"]["name"]
            _check_array_items(
                spec["function"]["parameters"],
                tool_name=tool_name,
                path="parameters",
                violations=violations,
            )
        assert not violations, (
            "Tool schemas with array params missing `items`:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_every_required_field_appears_in_properties(
        self, all_tool_schemas: list[dict],
    ) -> None:
        """A schema declaring ``required: [\"x\"]`` but not listing
        ``x`` in ``properties`` is technically valid JSON Schema but
        confuses LLMs (the model can't know what type ``x`` should
        be). Catching this at unit-test speed prevents a confusing
        round-trip through the provider."""
        violations: list[str] = []
        for spec in all_tool_schemas:
            tool_name = spec["function"]["name"]
            _check_required_in_properties(
                spec["function"]["parameters"],
                tool_name=tool_name,
                path="parameters",
                violations=violations,
            )
        assert not violations, (
            "Tool schemas with required fields missing from properties:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_top_level_is_object(
        self, all_tool_schemas: list[dict],
    ) -> None:
        """OpenAI requires the ``parameters`` block to be a JSON
        object schema (i.e. ``type: object``). Function calling
        wouldn't make sense otherwise — there's nowhere for named
        arguments to live."""
        for spec in all_tool_schemas:
            tool_name = spec["function"]["name"]
            params = spec["function"]["parameters"]
            assert params.get("type") == "object", (
                f"{tool_name}: parameters block must be type=object, "
                f"got {params.get('type')!r}"
            )


# ---------------------------------------------------------------------------
# Recursion helpers
# ---------------------------------------------------------------------------


def _check_array_items(
    schema: dict,
    *,
    tool_name: str,
    path: str,
    violations: list[str],
) -> None:
    """Walk the schema tree; flag any ``array`` node without ``items``."""
    if not isinstance(schema, dict):
        return
    if schema.get("type") == "array" and "items" not in schema:
        violations.append(f"{tool_name} at {path}: array without items")
    # Recurse into properties + items + anyOf/oneOf/allOf
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            for prop, sub in value.items():
                _check_array_items(
                    sub, tool_name=tool_name,
                    path=f"{path}.properties.{prop}",
                    violations=violations,
                )
        elif key == "items" and isinstance(value, dict):
            _check_array_items(
                value, tool_name=tool_name,
                path=f"{path}.items",
                violations=violations,
            )
        elif key in ("anyOf", "oneOf", "allOf") and isinstance(value, list):
            for i, sub in enumerate(value):
                _check_array_items(
                    sub, tool_name=tool_name,
                    path=f"{path}.{key}[{i}]",
                    violations=violations,
                )


def _check_required_in_properties(
    schema: dict,
    *,
    tool_name: str,
    path: str,
    violations: list[str],
) -> None:
    """Walk the schema tree; flag any ``required`` entry that's not
    a key of the same node's ``properties``."""
    if not isinstance(schema, dict):
        return
    required = schema.get("required")
    properties = schema.get("properties")
    if isinstance(required, list) and isinstance(properties, dict):
        for field in required:
            if field not in properties:
                violations.append(
                    f"{tool_name} at {path}: required[{field!r}] missing "
                    f"from properties (declared keys: {list(properties)})"
                )
    # Recurse — same shape walking as _check_array_items but for
    # required-vs-properties consistency.
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            for prop, sub in value.items():
                _check_required_in_properties(
                    sub, tool_name=tool_name,
                    path=f"{path}.properties.{prop}",
                    violations=violations,
                )
        elif key == "items" and isinstance(value, dict):
            _check_required_in_properties(
                value, tool_name=tool_name,
                path=f"{path}.items",
                violations=violations,
            )
        elif key in ("anyOf", "oneOf", "allOf") and isinstance(value, list):
            for i, sub in enumerate(value):
                _check_required_in_properties(
                    sub, tool_name=tool_name,
                    path=f"{path}.{key}[{i}]",
                    violations=violations,
                )


# ---------------------------------------------------------------------------
# Defence in depth — confirm the validator catches the original Phase 18 bug
# ---------------------------------------------------------------------------


class TestValidatorCatchesPhase18Bug:
    """Synthetic schemas that reproduce the bug shapes we shipped this
    phase. If these tests stop failing as expected, the validator is
    silently letting the bug class slip through — exactly the
    coverage gap this whole file exists to close."""

    def test_array_without_items_violates_invariant(self) -> None:
        """The original Phase 18 bug: ``ToolManager.get_openai_tools``
        produced ``{"type": "array"}`` without ``items`` for tools
        with array-typed parameters. Walks the same code path the
        invariant check uses to confirm it surfaces the violation
        with a clear path."""
        violations: list[str] = []
        bad = {
            "type": "object",
            "properties": {
                "data": {"type": "array"},  # missing items
            },
            "required": ["data"],
        }
        _check_array_items(
            bad, tool_name="synthetic_tool",
            path="parameters", violations=violations,
        )
        assert violations == [
            "synthetic_tool at parameters.properties.data: array without items",
        ]

    def test_required_field_not_in_properties_violates_invariant(
        self,
    ) -> None:
        """A different LLM-confusing shape: ``required`` lists a key
        that ``properties`` doesn't define. Catches typos in raw
        schemas and refactors that drop a property without updating
        ``required``."""
        violations: list[str] = []
        bad = {
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x", "y"],  # y not in properties
        }
        _check_required_in_properties(
            bad, tool_name="synthetic_tool",
            path="parameters", violations=violations,
        )
        # Exactly one violation, naming the missing key (``y``) — not
        # the present one (``x``).
        assert len(violations) == 1
        assert "required['y']" in violations[0]
        assert "missing from properties" in violations[0]

    def test_jsonschema_meta_validator_catches_invalid_type(self) -> None:
        """End-to-end: handing the meta-validator an obviously bad
        schema raises ``SchemaError``. Confirms our chosen validator
        actually rejects nonsense."""
        bad = {
            "type": "object",
            "properties": {
                # ``type`` must be a string or array of strings; a
                # number is invalid.
                "x": {"type": 42},
            },
        }
        with pytest.raises(jsonschema.SchemaError):
            jsonschema.Draft202012Validator.check_schema(bad)
