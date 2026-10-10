"""Natural-language end-to-end pilot freeze shape (desktop mocked in test_native)."""

import pytest
from agent_computer_use.contracts import GoalContract


def test_nl_pilot_freeze_covers_three_intake_cases(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s4_nl

    frozen = s4_nl.prepare(tmp_path / "pilot")
    assert [case["id"] for case in frozen["cases"]] == [
        "calculator-nl", "textedit-nl", "textedit-generic-nl"]
    assert frozen["revision"] == "s4-nl-1"
    assert frozen["request_limit"] == sum(case["max_decisions"] for case in frozen["cases"])
    assert any(path.endswith("/intake.py") for path in frozen["source_sha256"])
    assert s4_nl.load_freeze(tmp_path / "pilot", frozen["sha256"]) == frozen
    with pytest.raises(ValueError, match="freeze"):
        s4_nl.load_freeze(tmp_path / "pilot", "wrong")
    for case in frozen["cases"]:
        prompt = s4_nl.task_prompt(case)
        assert "schema_version" not in prompt
        task_input = s4_nl.task_input(case)
        assert set(task_input) == {"target"}
        brief = s4_nl.frozen_brief(case)
        GoalContract.from_input(s4_nl.goal_from_case(case))
        assert brief["application"]
        assert all(item["type"] in {"present", "absent", "title"} for item in brief["completion"])
        if case["id"] != "calculator-nl":
            assert any(prompt.find(item["value"]) >= 0 for item in brief["inputs"]
                       if item.get("value"))
