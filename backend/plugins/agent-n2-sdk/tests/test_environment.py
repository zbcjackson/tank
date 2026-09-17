"""Exercise actual SDK subprocess startup without a desktop or model call."""

import sys
from pathlib import Path

import pytest
from yutori.navigator.macos.transport import CuaDriverConnectionError
from yutori.navigator.macos.transport import CuaDriverUncertainActionError

from agent_n2_sdk.environment import CheckedTransport


@pytest.mark.parametrize(
    "detail",
    ["CuaDriver.app is not installed", "x" * 20000],
    ids=["missing-app", "long-stderr"],
)
async def test_startup_failure_preserves_bounded_driver_stderr(
    tmp_path, monkeypatch, detail
):
    binary = tmp_path / "driver"
    binary.write_text(
        f"#!{sys.executable}\nimport sys\nsys.stdin.readline()\n"
        f"sys.stderr.write({detail!r})\nsys.stderr.flush()\nsys.exit(1)\n"
    )
    binary.chmod(0o755)
    monkeypatch.setattr(
        "yutori.navigator.macos.transport.find_cua_driver_binary", lambda: Path(binary)
    )
    transport = CheckedTransport()
    with pytest.raises(CuaDriverConnectionError) as error:
        await transport.start()
    message = str(error.value)
    assert "status 1" in message
    assert detail[-8192:] in message
    assert len(message) < 9000
    assert not transport.running
    await transport.close()


async def test_startup_failure_without_stderr_includes_readiness_check(
    tmp_path, monkeypatch
):
    binary = tmp_path / "driver"
    binary.write_text(
        f"#!{sys.executable}\nimport sys\nsys.stdin.readline()\nsys.exit(1)\n"
    )
    binary.chmod(0o755)
    monkeypatch.setattr(
        "yutori.navigator.macos.transport.find_cua_driver_binary", lambda: binary
    )
    with pytest.raises(CuaDriverConnectionError, match="cua-driver doctor"):
        await CheckedTransport().start()


@pytest.mark.parametrize(
    "tool,read_only", [("get_desktop_state", True), ("click", False)]
)
async def test_rpc_timeout_does_not_reconnect_or_replay_session(
    tmp_path, monkeypatch, tool, read_only
):
    import json

    log = tmp_path / "calls.jsonl"
    binary = tmp_path / "driver"
    binary.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"log = open({str(log)!r}, 'a', buffering=1)\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    log.write(json.dumps(request) + '\\n')\n"
        "    if 'id' not in request: continue\n"
        "    name = request.get('params', {}).get('name')\n"
        f"    if name == {tool!r}: continue\n"
        "    print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': {}}), flush=True)\n"
    )
    binary.chmod(0o755)
    monkeypatch.setattr(
        "yutori.navigator.macos.transport.find_cua_driver_binary", lambda: binary
    )
    transport = CheckedTransport()
    transport.request_timeout_seconds = 1
    try:
        await transport.call_tool("start_session", {"session": "task"})
        expected = (
            CuaDriverConnectionError if read_only else CuaDriverUncertainActionError
        )
        with pytest.raises(expected, match=tool):
            await transport.call_tool(
                tool, {"session": "task"}, read_only=read_only, timeout_seconds=0.01
            )
        # A failed transport may only finish cleanup, never begin another action.
        with pytest.raises(CuaDriverConnectionError):
            await transport.call_tool("click", {"session": "task"})
        await transport.call_tool("end_session", {"session": "task"})
    finally:
        await transport.close()
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert sum(call["method"] == "initialize" for call in calls) == 1
    tools = [call["params"]["name"] for call in calls if call["method"] == "tools/call"]
    assert tools == ["start_session", tool, "end_session"]
