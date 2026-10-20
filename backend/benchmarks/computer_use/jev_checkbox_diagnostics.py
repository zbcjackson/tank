"""No-model sqlite-web checkbox coverage and SQL column-effect diagnostics."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Awaitable
from contextlib import closing
from pathlib import Path
from typing import TypeVar
from unittest.mock import patch

from benchmarks.computer_use import jev_real_product_route as product

_T = TypeVar("_T")


def create_fixture(path: Path, records: list[dict]) -> None:
    product.create_database(path, records)
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE _column_writes(column_name TEXT, id INTEGER, old_value TEXT, new_value TEXT)')
        for column in ('id', 'title', 'notes'):
            db.execute(f"CREATE TRIGGER column_{column} AFTER UPDATE OF {column} ON work_items BEGIN INSERT INTO _column_writes VALUES ('{column}',new.id,old.{column},new.{column}); END")
        db.commit()


def evidence(path: Path) -> dict:
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        return {'records': [dict(r) for r in db.execute('SELECT * FROM work_items ORDER BY id')],
                'writes': [dict(r) for r in db.execute('SELECT * FROM _writes ORDER BY rowid')],
                'column_writes': [dict(r) for r in db.execute('SELECT * FROM _column_writes ORDER BY column_name,rowid')],
                'schema': [list(r) for r in db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name')]}


def freeze_inputs(app_python: Path, *, include_host: bool = False) -> dict:
    from benchmarks.computer_use.jev_image_dev import digest
    base = product.freeze_inputs(app_python)
    cases = []
    for actor in (('manual', 'host') if include_host else ('manual',)):
        for case in base['cases']:
            if case['kind'] != 'update' or case['recovery']:
                continue
            for mode in ('all', 'title'):
                goal = {**case['goal'], 'scope': 'checkbox-diagnostic'}
                if actor == 'host':
                    goal = {**goal, 'completion': [*goal['completion'], {'key': 'status:Written columns', 'value': '["title"]'}],
                            'constraints': [*goal['constraints'], 'Only title may appear in the SQL UPDATE; do not enable id or notes.']}
                cases.append({**case, 'id': f'{actor}-{mode}-{case["order"]}', 'mode': mode, 'actor': actor, 'goal': goal})
    f = {'revision': 'checkbox-diagnostic-1', 'no_models': True, 'include_host': include_host, 'cases': cases,
         'app': base['app'], 'versions': base['versions'], 'source_sha256': {**base['source_sha256'],
             str(Path(__file__).relative_to(product.ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
         'scope': 'owned sqlite-web forms and synthetic databases; scripted UI inputs, no model accuracy measurement'}
    f['sha256'] = digest(f)
    return f


async def run_case(case: dict, output: Path, *, app_python: Path, app: dict) -> dict:
    from dataclasses import asdict, replace
    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel
    from agent_computer_use.contracts import GoalContract, Fact, DecisionResult
    from agent_computer_use.controller import ComputerUseController
    from agent_computer_use.visual_selector import VisualSelector
    from agent_computer_use.action_builder import ActionBuilder
    from agent_computer_use.model_view import decision_question
    path = output / case['id']
    path.mkdir()
    database = path / 'fixture.db'
    row = {'id': case['id'], 'order': case['order'], 'mode': case['mode'], 'actor': case['actor'], 'status': 'started',
           'input_attempts': 0, 'inputs': [], 'events': [], 'captures': [], 'cleanup_confirmed': False}
    started = time.monotonic()
    class Observer:
        def on_event(self, kind, metadata):
            row['events'].append({'kind': kind, **metadata})
    async def audit(record):
        with (path/'audit.jsonl').open('a') as journal:
            journal.write(json.dumps(asdict(record))+'\n')
    ctx = SubAgentContext(SubAgentAuthorization(frozenset({'desktop', 'network'})), SubAgentBudget(),
                          asyncio.Event(), observer=Observer(), audit=audit, deadline=started+120, max_actions=6, max_observations=24)
    ctx.runtime.bind('diagnostic-' + case['id'])
    process = browser = app_log = None
    contract = GoalContract.from_input({**case['goal'], 'scope': 'checkbox-diagnostic'})
    async def save_frame(stage, observed, offered):
        assert browser is not None and browser.page is not None
        frame = await browser.capture(observed, ctx)
        (path / (stage+'.png')).write_bytes(frame.png)
        record = {'stage': stage, 'packet': decision_question(contract, observed, offered),
                  'reason': offered.reason, 'candidate_count': len(offered.actions),
                  'column_candidates': sum(d.role == 'checkbox' and d.label.startswith('Allow updating this column.') for d in offered.details),
                  'bounds': dict(frame.bounds), 'image_sha256': hashlib.sha256(frame.png).hexdigest()}
        row['captures'].append(record)
    async def snapshot(stage):
        assert browser is not None
        observed = await browser.observe(contract.scope, ctx)
        offered = ActionBuilder(visual=True).build(contract.goal_id, 1, contract, observed)
        await save_frame(stage, observed, offered)
    class ReceiptChannel(ManagedChromiumChannel):
        async def observe(self, scope, context):
            observed = await super().observe(scope, context)
            actual = await asyncio.to_thread(evidence, database)
            columns = sorted({w['column_name'] for w in actual['column_writes']})
            self.previous = replace(observed, facts=(*observed.facts,
                Fact(key='status:Records', value=product.encoded(actual['records'])),
                Fact(key='status:Written columns', value=json.dumps(columns, separators=(',', ':')))))
            return self.previous
    class ScriptedVisual(VisualSelector):
        async def choose(self, goal, snapshot, actions, context):
            await save_frame('proposal-'+str(len(row.get('proposals', []))+1), snapshot, actions)
            detail = next((d for d in actions.details if d.input_key == 'title'), None)
            if detail is None:
                label = 'include all columns' if case['mode'] == 'all' else 'Allow updating this column. [name=chk_title]'
                detail = next((d for d in actions.details if d.role == 'checkbox' and d.label == label and d.current_value == 'false'), None)
            if detail is None:
                detail = next((d for d in actions.details if d.role == 'button' and d.label == 'Update'), None)
            if detail is None:
                return DecisionResult(actions.binding, 'none')
            row.setdefault('proposals', []).append({'binding': asdict(actions.binding), 'action_id': detail.action_id, 'label': detail.label})
            return DecisionResult(actions.binding, 'candidate', detail.action_id)
    async def close_owned():
        errors = []
        for close in ([ctx.runtime.aclose] + ([browser.aclose] if browser is not None else [])):
            try:
                await close()
            except (Exception, asyncio.CancelledError) as exc:
                errors.append(type(exc).__name__)
        if process is not None:
            if process.returncode is None:
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                process.kill()
                await process.wait()
                errors.append('product_termination_timeout')
        if app_log is not None:
            app_log.close()
        return errors
    interrupted = False
    async def finish(operation: Awaitable[_T]) -> _T:
        nonlocal interrupted
        pending = asyncio.ensure_future(operation)
        while True:
            try:
                return await asyncio.shield(pending)
            except asyncio.CancelledError:
                if pending.cancelled():
                    raise
                interrupted = True
    try:
        await asyncio.to_thread(create_fixture, database, case['seed'])
        row['initial_evidence'] = await asyncio.to_thread(evidence, database)
        app_log = (path / 'app.log').open('wb')
        process = await asyncio.create_subprocess_exec(str(app_python), str(Path(product.__file__)), '--serve',
            '--database', str(database), '--output', str(path), cwd=path, stdout=app_log,
            stderr=asyncio.subprocess.STDOUT, env={'PATH': os.environ.get('PATH', ''), 'PYTHONUNBUFFERED': '1'})
        async with asyncio.timeout(10):
            while True:
                ready = path / 'ready.json'
                if ready.exists():
                    try:
                        port = json.loads(ready.read_text())['port']
                        break
                    except json.JSONDecodeError:
                        pass
                if process.returncode is not None:
                    raise RuntimeError('product exited before ready')
                await asyncio.sleep(.02)
        url = f'http://127.0.0.1:{port}' + case['start_path']
        channel_type = ReceiptChannel if case['actor'] == 'host' else ManagedChromiumChannel
        browser = channel_type(BrowserConfig(scope=contract.scope, url=url))
        await snapshot('initial')
        page = browser.page
        assert page is not None
        row['native_checkboxes'] = await page.locator('input[type=checkbox]').evaluate_all(
            'nodes => nodes.map(n=>({name:n.name,label:n.getAttribute("aria-label")||"",checked:n.checked,disabled:n.disabled}))')
        if case['actor'] == 'host':
            host = ComputerUseController(browser, browser, selector=ScriptedVisual(browser))
            from tank_backend.agents.subagent import SubAgentRequest
            result = await host.run(SubAgentRequest(contract.intent, '', ctx.runtime.task_id, contract.model_dump(mode='json')), ctx)
            row['host_result'] = result.to_output().metadata['task_result']
            row['input_attempts'] = len(host.receipts)
            row['inputs'] = row['host_result']['details']['progress']['recent_steps']
        else:
            checkbox = (page.get_by_role('checkbox', name='include all columns', exact=True)
                        if case['mode'] == 'all' else page.locator('input[name=chk_title]'))
            operations = [('checkbox', checkbox.click), ('title', lambda: page.get_by_role('textbox', name='title', exact=True).fill(case['goal']['inputs'][0]['value'])),
                          ('submit', page.get_by_role('button', name='Update', exact=True).click)]
            for label, operation in operations:
                ctx.check('desktop')
                row['input_attempts'] += 1
                attempt = {'operation': label, 'status': 'unknown'}
                row['inputs'].append(attempt)
                await operation()
                attempt['status'] = 'returned'
                ctx.check('desktop')
                if label == 'checkbox':
                    await snapshot('checked')
            await page.wait_for_url('**/work_items/content/**', wait_until='load', timeout=5000)
        await snapshot('final')
        row['status'] = 'finished'
    except asyncio.CancelledError:
        interrupted = True
        row['status'] = 'cancelled'
    except Exception as exc:
        row.update(status='error', error_type=type(exc).__name__)
    finally:
        errors = await finish(close_owned())
        row['cleanup_errors'] = errors
        row['cleanup_confirmed'] = not errors and (process is None or process.returncode is not None) and (browser is None or browser.closed and (browser.browser is None or not browser.browser.is_connected()))
        try:
            row['evidence'] = await finish(asyncio.to_thread(evidence, database))
            row['app_unchanged'] = await finish(asyncio.to_thread(product.app_manifest, app_python)) == app
        except Exception as exc:
            row.update(status='error', readback_error_type=type(exc).__name__, evidence=None, app_unchanged=False)
        if interrupted:
            row['status'] = 'cancelled'
        if 'host_result' in row:
            row['host_result']['cleanup'] = 'confirmed' if row['cleanup_confirmed'] else 'unknown'
        row['usage'] = ctx.budget.snapshot()
        row['model_calls'] = sum(e['kind'] == 'model_call' and e.get('phase') == 'started' for e in row['events'])
        row['http'] = [json.loads(line) for line in (path/'http.jsonl').read_text().splitlines()] if (path/'http.jsonl').exists() else []
        row['value_success'] = bool(row['status'] == 'finished' and row['cleanup_confirmed'] and row['app_unchanged']
            and row['evidence'] is not None and row['evidence']['records'] == case['oracle']['rows'] and len(row['evidence']['writes']) == 1
            and row['evidence']['writes'][0]['operation'] == 'update'
            and row['evidence']['schema'] == row['initial_evidence']['schema']
            and sum(r['method'] == 'POST' for r in row['http']) == 1)
        row['column_success'] = bool(row['value_success'] and row['evidence'] is not None and [w['column_name'] for w in row['evidence']['column_writes']] == ['title'])
        row['elapsed_ms'] = (time.monotonic()-started)*1000
        (path/'row.json').write_text(json.dumps(row, ensure_ascii=False, indent=2)+'\n')
    if interrupted:
        raise asyncio.CancelledError
    return row


async def run(output: Path, *, app_python: Path, include_host: bool = False) -> dict:
    import httpx
    import httpx2
    frozen = freeze_inputs(app_python, include_host=include_host)
    output.mkdir(parents=True, exist_ok=False)
    (output/'freeze.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2)+'\n')
    for name, sha in frozen['source_sha256'].items():
        data = (product.ROOT/name).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError('source changed before diagnostic')
        target = output/'source'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    attempts = []
    def forbidden(*args, **kwargs):
        attempts.append('HTTP client construction')
        raise AssertionError('no-model diagnostic forbids SDK HTTP clients')
    result = {'sha256': frozen['sha256'], 'rows': [{'id': c['id'], 'status': 'not_run'} for c in frozen['cases']],
              'completed': False, 'model_calls': 0, 'client_attempts': attempts}
    try:
        with patch.object(httpx.AsyncClient, '__init__', forbidden), patch.object(httpx2.AsyncClient, '__init__', forbidden):
            for row, case in zip(result['rows'], frozen['cases'], strict=True):
                try:
                    if (json.loads((output/'freeze.json').read_text()) != frozen
                            or any(hashlib.sha256((product.ROOT/name).read_bytes()).hexdigest() != sha
                                   for name, sha in frozen['source_sha256'].items())):
                        raise ValueError('diagnostic freeze changed')
                    row.update(await run_case(case, output, app_python=app_python, app=frozen['app']))
                except asyncio.CancelledError:
                    saved = output/case['id']/'row.json'
                    row.update(json.loads(saved.read_text()) if saved.exists() else {'status': 'cancelled'})
                    raise
                except Exception as exc:
                    row.update(status='error', error_type=type(exc).__name__, cleanup_confirmed=False)

                if row['status'] != 'finished' or not row['cleanup_confirmed'] or not row['app_unchanged']:
                    break
        result['completed'] = all(r['status'] == 'finished' for r in result['rows'])
    finally:
        result['model_calls'] = sum(r.get('model_calls', 0) for r in result['rows'])
        (output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    return result


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--app-python', required=True, type=Path)
    parser.add_argument('--include-host', action='store_true')
    args = parser.parse_args()
    result = asyncio.run(run(args.output, app_python=args.app_python, include_host=args.include_host))
    print(json.dumps({'completed': result['completed'], 'model_calls': result['model_calls']}))


if __name__ == '__main__':
    main()
