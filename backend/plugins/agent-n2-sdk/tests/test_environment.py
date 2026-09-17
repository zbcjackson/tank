"""Exercise actual SDK subprocess startup without a desktop or model call."""

import sys
from pathlib import Path

import pytest
from yutori.navigator.macos.transport import CuaDriverConnectionError

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
