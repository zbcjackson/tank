"""Scripted original-product qualification with bound candidates/PNG and no models."""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import http.client
import json
import os
import time
from collections.abc import Awaitable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel

from agent_computer_use.action_builder import ActionBuilder
from agent_computer_use.channels.dom import BrowserConfig
from agent_computer_use.contracts import GoalContract
from agent_computer_use.visual_selector import VisualSelector
from tank_backend.agents.subagent import (
    SubAgentAuthorization,
    SubAgentBudget,
    SubAgentContext,
    SubAgentStopped,
)
from tank_backend.llm.model_data import ModelDataScope
from benchmarks.computer_use import jev_audit as audit
from benchmarks.computer_use import jev_calibration_route as calibration
from benchmarks.computer_use import jev_qualification as qualification


def _serial(value: object) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(type(value).__name__)


def persist(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            value, ensure_ascii=False, indent=2, default=_serial, allow_nan=False
        )
        + "\n"
    )
    temporary.replace(path)


async def run_case(case: dict, output: Path, frozen: dict) -> dict[str, Any]:
    if case not in frozen["cases"] or frozen["kind"] != "qualification-only":
        raise ValueError("only frozen qualification cases may run")
    path = output / case["id"]
    path.mkdir(exist_ok=False)
    row: dict[str, Any] = {
        "id": case["id"],
        "product": case["product"],
        "group": case["group"],
        "status": "started",
        "qualified": False,
        "cleanup": False,
        "observations": [],
        "events": [],
        "model_calls": 0,
    }
    started = time.monotonic()
    app_python = Path(frozen["apps"][case["product"]]["python"])
    adapter = (
        calibration.LinkdingCalibrationAdapter(app_python, case["fault_path"])
        if case["product"] == "linkding"
        else calibration.SQLiteAdapter(case["fault_path"])
    )
    database = None
    process = channel = context = None
    app_log = None
    errors = []
    cleanup_interrupted = False

    async def finish_cleanup(operation: Awaitable[object]) -> None:
        nonlocal cleanup_interrupted
        cleanup_interrupted |= await calibration.shared.settle_cleanup(operation)

    try:
        async with asyncio.timeout(45):
            database = await adapter.initialize(path, app_python, case)
            calibration.shared.backup_database(database, path / "before.db")
            app_log = (path / "app.log").open("wb")
            process = await asyncio.create_subprocess_exec(
                *adapter.server_command(app_python, database, path),
                cwd=adapter.server_directory(database, path),
                env={"PATH": os.environ.get("PATH", ""), "PYTHONUNBUFFERED": "1"},
                stdout=app_log,
                stderr=asyncio.subprocess.STDOUT,
            )
            async with asyncio.timeout(15):
                while not (path / "ready.json").exists():
                    if process.returncode is not None:
                        raise RuntimeError("product exited before ready")
                    await asyncio.sleep(0.02)
            port = json.loads((path / "ready.json").read_text())["port"]
            origin = f"http://127.0.0.1:{port}"
            if case["condition"] == "prewarmed":

                def warm() -> None:
                    connection = http.client.HTTPConnection(
                        "127.0.0.1", port, timeout=3
                    )
                    try:
                        connection.request(
                            "GET", "/login/" if case["product"] == "linkding" else "/"
                        )
                        response = connection.getresponse()
                        response.read()
                        if not 200 <= response.status < 400:
                            raise RuntimeError("prewarm failed")
                    finally:
                        connection.close()

                await asyncio.to_thread(warm)

            class Observer:
                def on_event(self, kind, metadata):
                    row["events"].append({"kind": kind, **metadata})

            context = SubAgentContext(
                SubAgentAuthorization(frozenset({"desktop", "network"})),
                SubAgentBudget(),
                asyncio.Event(),
                observer=Observer(),
                model_data_scope=ModelDataScope(frozenset({"text", "image"}), 33554432),
            )
            context.runtime.bind(case["id"])
            channel = adapter.channel(
                BrowserConfig(
                    scope=case["goal"]["scope"], url=origin + case["start_path"]
                ),
                database,
                row,
            )
            visual = VisualSelector(channel)
            visual.register(context)
            goal = GoalContract.from_input(case["goal"])
            await channel.start(context)
            page = channel.page
            if page is None:
                raise RuntimeError("product page unavailable")

            async def observe(phase: str) -> Any:
                await page.wait_for_load_state("load", timeout=5000)
                snapshot = await channel.observe(goal.scope, context)
                actions = ActionBuilder(64, visual=True).build(
                    case["id"], 1, goal, snapshot
                )
                entry = {
                    "phase": phase,
                    "snapshot": snapshot,
                    "actions": actions,
                    "capture": "refused",
                }
                row["observations"].append(entry)
                try:
                    frame = await visual.capture_frame(snapshot, actions, context)
                    name = f"{len(row['observations']):02}-{phase}.png"
                    (path / name).write_bytes(frame.png)
                    entry.update(
                        capture="accepted",
                        png=name,
                        png_sha256=hashlib.sha256(frame.png).hexdigest(),
                    )
                except Exception as error:
                    entry.update(error_type=type(error).__name__)
                persist(path / "row.json", row)
                return actions

            if case["recovery"] and case["fault_stage"] == "list":
                await page.get_by_role("link", name="Retry", exact=True).wait_for(
                    timeout=5000
                )
                await observe("list-fault")
                await page.get_by_role("link", name="Retry", exact=True).click(
                    timeout=5000
                )
            await observe("list")
            if case["negative"] == "missing":
                row["missing_target"] = True
            elif case["negative"] == "revoked":
                await page.goto(origin + case["oracle"]["edit_path"], timeout=5000)
                actions = await observe("revocation-editor")
                action = next(a for a in actions.actions if a.operation == "click")
                context.authorization.revoke()
                try:
                    await channel.dispatch(actions.binding, action, context)
                except SubAgentStopped as error:
                    row["revocation"] = {
                        "authorization_active": context.authorization.active,
                        "error_type": type(error).__name__,
                    }
                else:
                    raise RuntimeError("revoked dispatch unexpectedly returned")
            else:
                if case["product"] == "linkding":
                    await (
                        page.locator(f'li[data-bookmark-id="{case["target"]}"]')
                        .get_by_role("link", name="Edit", exact=True)
                        .click(timeout=5000)
                    )
                else:
                    await page.locator(
                        f'a[href="{case["oracle"]["edit_path"]}"]'
                    ).click(timeout=5000)
                if case["recovery"] and case["fault_stage"] == "editor":
                    await page.get_by_role("link", name="Retry", exact=True).wait_for(
                        timeout=5000
                    )
                    await observe("editor-fault")
                    await page.get_by_role("link", name="Retry", exact=True).click(
                        timeout=5000
                    )
                title = page.get_by_label(
                    "Title" if case["product"] == "linkding" else "title", exact=True
                )
                await title.wait_for(state="visible", timeout=5000)
                await observe("editor")
                if case["product"] == "sqlite-web":
                    await page.locator('input[name="chk_title"]').check(timeout=5000)
                    await observe("title-enabled")
                await title.fill(
                    next(
                        x["value"]
                        for x in case["goal"]["inputs"]
                        if x["key"] == "title"
                    ),
                    timeout=5000,
                )
                await observe("filled")
                await page.get_by_role(
                    "button",
                    name="Save" if case["product"] == "linkding" else "Update",
                    exact=True,
                ).click(timeout=5000)
                await page.wait_for_url(
                    lambda url: urlsplit(url).path == case["start_path"], timeout=5000
                )
                await observe("returned")
            row["final_url"] = page.url
            (path / "final.html").write_text(await page.content(), encoding="utf-8")
            row["status"] = "finished"
    except asyncio.CancelledError:
        row["status"] = "cancelled"
        raise
    except Exception as error:
        row.update(status="error", error_type=type(error).__name__, error=str(error))
    finally:
        for close in ([context.runtime.aclose] if context else []) + (
            [channel.aclose] if channel else []
        ):
            try:
                await finish_cleanup(close())
            except (Exception, asyncio.CancelledError) as error:
                errors.append(type(error).__name__)
                cleanup_interrupted |= isinstance(error, asyncio.CancelledError)
        if process is not None:
            if process.returncode is None:
                process.terminate()
            try:
                await finish_cleanup(asyncio.wait_for(process.wait(), 5))
            except TimeoutError:
                process.kill()
                await finish_cleanup(process.wait())
                errors.append("termination_timeout")
        if app_log is not None:
            app_log.close()
        if database is not None and database.exists():
            calibration.shared.backup_database(database, path / "after.db")
        if cleanup_interrupted:
            row["status"] = "cancelled"
        persist(path / "events.json", row["events"])
        persist(path / "observations.json", row["observations"])
        row["model_calls"] = sum(e["kind"] == "model_call" for e in row["events"])
        row["cleanup"] = bool(
            not errors
            and channel is not None
            and channel.closed
            and process is not None
            and process.returncode is not None
        )
        proof = {
            "process_returncode": process.returncode if process else None,
            "channel_closed": channel.closed if channel else False,
            "browser_closed": bool(
                channel
                and (channel.browser is None or not channel.browser.is_connected())
            ),
            "cleanup_errors": errors,
            "files": {
                name: qualification.sha(path / name)
                for name in (
                    "before.db",
                    "after.db",
                    "http.jsonl",
                    "final.html",
                    "events.json",
                    "observations.json",
                )
                if (path / name).is_file()
            },
        }
        persist(path / "native-proof.json", proof)
        row["elapsed_ms"] = (time.monotonic() - started) * 1000
        try:
            row["qualified"] = row["status"] == "finished" and audit.audit_native_trial(
                case, row, path
            )
        except Exception as error:
            row["audit_error"] = str(error)
        persist(path / "row.json", row)
        if cleanup_interrupted:
            raise asyncio.CancelledError
    return row


async def run(root: Path, approved: str) -> dict[str, Any]:
    frozen = qualification.load_freeze(root, approved)
    output = root / "native"
    output.mkdir(exist_ok=False)
    rows = [
        {
            "id": case["id"],
            "status": "not_run",
            "attempted": False,
            "qualified": False,
            "cleanup": False,
            "model_calls": 0,
        }
        for case in frozen["cases"]
    ]
    result = {"sha256": approved, "rows": rows, "completed": False, "model_calls": 0}
    persist(output / "result.json", result)

    def restore(row: dict) -> None:
        partial = output / row["id"] / "row.json"
        if partial.is_file():
            try:
                saved = json.loads(partial.read_text())
                if saved.get("id") == row["id"]:
                    row.update(saved)
            except (OSError, ValueError, TypeError):
                row["partial_receipt_unreadable"] = True

    for case, row in zip(frozen["cases"], rows):
        try:
            qualification.load_freeze(root, approved)
            row.update(status="started", attempted=True)
            persist(output / "result.json", result)
            row.update(await run_case(case, output, frozen))
        except asyncio.CancelledError:
            restore(row)
            row["status"] = "cancelled" if row["attempted"] else "not_run"
            result["stop_reason"] = "cancelled"
            raise
        except Exception as error:
            restore(row)
            row["status"] = "error" if row["attempted"] else "not_run"
            row["error_type"] = type(error).__name__
            result["stop_reason"] = (
                "operational_error" if row["attempted"] else "freeze_drift"
            )
        finally:
            persist(output / "result.json", result)
        if not row["qualified"]:
            break
    result["completed"] = all(row["qualified"] for row in rows)
    result["model_calls"] = sum(row["model_calls"] for row in rows)
    persist(output / "result.json", result)
    return result
