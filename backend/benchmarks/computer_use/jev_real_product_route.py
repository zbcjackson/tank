"""Frozen V/JT development comparison on an unmodified sqlite-web installation."""
from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable
from contextlib import closing
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def encoded(records: list[dict]) -> str:
    return json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def cases() -> list[dict]:
    import base64
    result = []
    for recovery, orders in ((False, range(2)), (True, range(1))):
        for order in orders:
            for kind in ('insert', 'update'):
                target = order + 1
                rows = [{'id': n, 'title': ('Draft' if n == target else 'Archive') + f' {order}',
                         'notes': f'Keep {order}/{n}'} for n in (1, 2)]
                after = [dict(r) for r in rows]
                title, note = f'Launch {order}', f'New note {order}'
                if kind == 'insert':
                    after.append({'id': 3, 'title': title, 'notes': note})
                    intent = f'Create one record in work_items with title {title!r} and notes {note!r}. Keep existing records unchanged.'
                else:
                    after[target - 1]['title'] = title
                    intent = f'Change only the title of work_items record id {target} from {rows[target-1]["title"]!r} to {title!r}. Keep its notes and all other records unchanged.'
                key = f'{kind}-{order}-' + ('recovery' if recovery else 'normal')
                inputs = [{'key': 'title', 'purpose': 'Requested title', 'field_label': 'title', 'value': title}]
                if kind == 'insert':
                    inputs.append({'key': 'notes', 'purpose': 'New record notes', 'field_label': 'notes', 'value': note})
                goal = {'schema_version': 2, 'goal_id': 'goal-' + hashlib.sha256(key.encode()).hexdigest()[:16],
                        'scope': 'real-product', 'authorization_ref': 'current_task', 'intent': intent, 'objective': intent,
                        'allowed_operations': ['click', 'fill'], 'constraints': ['Do not delete records or change schema. Do not execute SQL.'],
                        'inputs': inputs, 'completion': [{'key': 'status:Records', 'value': encoded(after)}]}
                token = base64.urlsafe_b64encode(f'[{target}]'.encode()).decode().rstrip('=')
                start_path = '/work_items/insert/' if kind == 'insert' else f'/work_items/update/{token}/'
                result.append({'id': key, 'kind': kind, 'order': order, 'recovery': recovery, 'seed': rows, 'start_path': start_path,
                               'goal': goal, 'oracle': {'rows': after, 'operation': kind, 'writes': 1}})
    return result


def app_manifest(app_python: Path) -> dict:
    if not app_python.is_absolute() or not app_python.is_file():
        raise ValueError('absolute isolated app Python required')
    env = app_python.parent.parent
    sites = list((env / 'lib').glob('python*/site-packages'))
    if len(sites) != 1:
        raise ValueError('one isolated site-packages required')
    versions = {d.metadata['Name'].lower(): d.version for d in metadata.distributions(path=[str(sites[0])])}
    if versions.get('sqlite-web') != '0.8.1':
        raise ValueError('sqlite-web 0.8.1 required')
    files = {str(p.relative_to(env)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sites[0].rglob('*') if p.is_file() and '__pycache__' not in p.parts
             and p.suffix != '.pyc'}
    files['pyvenv.cfg'] = hashlib.sha256((env / 'pyvenv.cfg').read_bytes()).hexdigest()
    files['bin/python'] = hashlib.sha256(app_python.read_bytes()).hexdigest()
    return {'python': str(app_python), 'versions': versions, 'files': files}


def freeze_inputs(app_python: Path) -> dict:
    from benchmarks.computer_use import jev_vision_route as base
    from benchmarks.computer_use.jev_image_dev import digest
    items = cases()
    f = {'revision': 'real-product-1', 'cases': items,
         'schedule': [{'id': c['id'] + '-' + arm, 'case': c['id'], 'arm': arm}
                      for c in items for arm in (('v', 'jt') if (c['order'] + (c['kind'] == 'update')) % 2 == 0 else ('jt', 'v'))],
         'app': app_manifest(app_python), 'source_sha256': {**base.sources(),
             str(Path(__file__).relative_to(ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
         'models': {'jev': base.JEV, 'peer': base.PEER}, 'record_only': True,
         'versions': {n: metadata.version(n) for n in ('playwright', 'openai', 'typesafe-sdk', 'pillow')},
         'seconds_per_task': 120, 'max_actions': 6, 'max_observations': 24, 'retries': 0,
         'scope': 'unmodified local sqlite-web; synthetic records only; Jev text and Gemini PNG+text',
         'business_evidence': 'read-only actual work_items rows, no expected-data comparison in observer',
         'recovery': 'first form GET returns injected 503 without forwarding; Retry adds retry=1; no POST retry; direct form starts in both conditions',
         'price_nano_usd': {'jev': [42, 0], 'peer': [825, 4125]},
         'price_evidence': 'historical frozen estimate, not an invoice'}
    f['sha256'] = digest(f)
    return f


def prepare(output: Path, *, app_python: Path) -> dict:
    f = freeze_inputs(app_python)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'freeze.json').write_text(json.dumps(f, ensure_ascii=False, indent=2) + '\n')
    return f


def load_freeze(output: Path, approved: str) -> dict:
    stored = json.loads((output / 'freeze.json').read_text())
    f = freeze_inputs(Path(stored['app']['python']))
    if stored != f or f['sha256'] != approved:
        raise ValueError('real-product freeze changed')
    return f


def create_database(path: Path, records: list[dict]) -> None:
    import sqlite3
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE work_items(id INTEGER PRIMARY KEY, title TEXT NOT NULL, notes TEXT NOT NULL)')
        db.executemany('INSERT INTO work_items VALUES (:id,:title,:notes)', records)
        db.execute('CREATE TABLE _writes(operation TEXT, id INTEGER, old_title TEXT, new_title TEXT, old_notes TEXT, new_notes TEXT)')
        for op in ('insert', 'update', 'delete'):
            old = 'NULL,NULL' if op == 'insert' else 'old.title,old.notes'
            new = 'NULL,NULL' if op == 'delete' else 'new.title,new.notes'
            old_title, old_note = old.split(',')
            new_title, new_note = new.split(',')
            identity = 'old.id' if op == 'delete' else 'new.id'
            db.execute(f"CREATE TRIGGER log_{op} AFTER {op} ON work_items BEGIN INSERT INTO _writes VALUES ('{op}',{identity},{old_title},{new_title},{old_note},{new_note}); END")
        db.commit()


def database_state(path: Path) -> dict:
    import sqlite3
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        return {'records': [dict(r) for r in db.execute('SELECT * FROM work_items ORDER BY id')],
                'writes': [dict(r) for r in db.execute('SELECT * FROM _writes ORDER BY rowid')],
                'schema': [list(r) for r in db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name')]}


def serve_product(database: Path, output: Path, fault_path: str | None) -> None:
    """Run the upstream app unchanged; middleware records HTTP and injects one GET refusal."""
    import importlib
    import sys
    product = importlib.import_module('sqlite_web.sqlite_web')
    serving = importlib.import_module('werkzeug.serving')
    sys.argv = ['sqlite_web', str(database), '-x', '-q']
    product.configure_app()
    failed = False
    def middleware(environ, start_response):
        nonlocal failed
        method, path = environ['REQUEST_METHOD'], environ['PATH_INFO']
        query = environ.get('QUERY_STRING', '')
        injected = bool(fault_path and not failed and method == 'GET' and path == fault_path)
        def record(status, headers, exc_info=None):
            with (output / 'http.jsonl').open('a') as journal:
                journal.write(json.dumps({'method': method, 'path': path, 'query': query, 'status': status, 'injected': injected}) + '\n')
            return start_response(status, headers, exc_info)
        if injected:
            failed = True
            body = b'<!doctype html><title>Temporary service failure</title><h1>Service unavailable</h1><p>This GET was not forwarded. Retry to continue.</p><a href="?retry=1">Retry</a>'
            record('503 Service Unavailable', [('Content-Type', 'text/html; charset=utf-8'), ('Content-Length', str(len(body)))])
            return [body]
        return product.app(environ, record)
    server = serving.make_server('127.0.0.1', 0, middleware)
    (output / 'ready.json').write_text(json.dumps({'port': server.server_port}) + '\n')
    server.serve_forever()


async def run_task(case: dict, arm: str, output: Path, *, app_python: Path,
                   jev_credential: str, peer_credential: str, ledger=None) -> dict:
    import base64
    import os
    import time
    from dataclasses import asdict, replace
    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext, SubAgentRequest
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.model_data import ModelDataScope
    from tank_backend.llm.profile import LLMProfile
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel
    from agent_computer_use.contracts import Fact
    from agent_computer_use.controller import ComputerUseController
    from agent_computer_use.visual_selector import VisualSelector
    from benchmarks.computer_use import jev_vision_route as base
    from benchmarks.computer_use.jev_image_dev import digest
    if arm not in ('v', 'jt') or not jev_credential.strip() or not peer_credential.strip():
        raise ValueError('declared arm and both credentials required')
    row_id = case['id'] + '-' + arm
    task_id = 'product-' + hashlib.sha256(row_id.encode()).hexdigest()[:16]
    path = output / row_id
    path.mkdir(exist_ok=False)
    started = time.monotonic()
    app_before = app_manifest(app_python)
    own_ledger = ledger is None
    if ledger is None:
        ledger = SpendLedger(SpendLimit(0, 0), record_only=True, journal=path / 'spend.jsonl')
    ledger.start_trial(row_id, SpendLimit(0, 0))
    row = {'id': row_id, 'case': case['id'], 'task_id': task_id, 'arm': arm, 'kind': case['kind'],
           'recovery': case['recovery'], 'status': 'started', 'strict_completed': False,
           'recovery_completed': False, 'cleanup_confirmed': False, 'events': [], 'calls': []}
    database = path / 'fixture.db'
    create_database(database, case['seed'])
    initial_schema = database_state(database)['schema']
    process = channel = ctx = None
    app_log = None
    class ProductChannel(ManagedChromiumChannel):
        async def observe(self, scope, context):
            snapshot = await super().observe(scope, context)
            actual = await asyncio.to_thread(database_state, database)
            self.previous = replace(snapshot, facts=(*snapshot.facts, Fact(key='status:Records', value=encoded(actual['records']))))
            return self.previous
    class Observer:
        def on_event(self, kind, metadata):
            row['events'].append({'kind': kind, **metadata})
    class Capture:
        async def request(self, call_id, request):
            item = {'call_id': call_id, 'request': request.parameters, 'images': []}
            for message in request.parameters.get('messages', []):
                if isinstance(message['content'], list):
                    for part in message['content']:
                        if part['type'] == 'image_url':
                            png = base64.b64decode(part['image_url']['url'].split(',', 1)[1])
                            name = f'{call_id}.png'
                            (path / name).write_bytes(png)
                            item['images'].append({'path': name, 'sha256': hashlib.sha256(png).hexdigest()})
            row['calls'].append(item)
            with (path / 'calls.jsonl').open('a') as journal:
                journal.write(json.dumps(item, ensure_ascii=False) + '\n')
        async def response(self, call_id, response):
            with (path / 'calls.jsonl').open('a') as journal:
                journal.write(json.dumps({'call_id': call_id, 'response': response}, ensure_ascii=False) + '\n')
    async def audit(record):
        with (path / 'audit.jsonl').open('a') as journal:
            journal.write(json.dumps(asdict(record)) + '\n')
    cleanup_interrupted = False
    async def finish_cleanup(operation: Awaitable[object]) -> None:
        nonlocal cleanup_interrupted
        pending = asyncio.ensure_future(operation)
        while True:
            try:
                await asyncio.shield(pending)
                return
            except asyncio.CancelledError:
                if pending.cancelled():
                    raise
                cleanup_interrupted = True
    try:
        app_log = (path / 'app.log').open('wb')
        process = await asyncio.create_subprocess_exec(str(app_python), str(Path(__file__)), '--serve',
            '--database', str(database), '--output', str(path), *(['--fault-path', case['start_path']] if case['recovery'] else []),
            stdout=app_log, stderr=asyncio.subprocess.STDOUT, cwd=path,
            env={'PATH': os.environ.get('PATH', ''), 'PYTHONUNBUFFERED': '1'})
        async with asyncio.timeout(10):
            while not (path / 'ready.json').exists():
                if process.returncode is not None:
                    raise RuntimeError('product process exited before ready')
                await asyncio.sleep(.02)
        port = json.loads((path / 'ready.json').read_text())['port']
        channel = ProductChannel(BrowserConfig(scope='real-product', url=f'http://127.0.0.1:{port}' + case['start_path']))
        selector = base.VisionBaseline(channel) if arm == 'v' else VisualSelector(channel)
        host = ComputerUseController(channel, channel, selector=selector)
        ctx = SubAgentContext(SubAgentAuthorization(frozenset({'desktop', 'network'})), SubAgentBudget(),
            asyncio.Event(), deadline=started + 120, max_actions=6, max_observations=24,
            model_data_scope=ModelDataScope(frozenset({'text', 'image'}), 32 * 1024 * 1024),
            observer=Observer(), audit=audit, model_capture=Capture(), model_policy=BenchmarkModelPolicy(ledger, ()))
        ctx.runtime.configure_decision_model(task_id, DecisionModelProfile(base.JEV['url'], base.JEV['model'], 'TYPESAFE_API_KEY'), credential=jev_credential)
        ctx.runtime.configure_visual_model(task_id, LLMProfile('product-peer', peer_credential, base.PEER['model'], base.PEER['url'], temperature=0, max_tokens=base.PEER['max_tokens']))
        result = await host.run(SubAgentRequest(case['goal']['intent'], '', task_id, case['goal']), ctx)
        row['result'] = result.to_output().metadata['task_result']
        row['status'] = 'finished'
        if channel.page is not None:
            row['final_url'] = channel.page.url
            (path / 'final.png').write_bytes(await channel.page.screenshot(type='png', scale='css'))
        if result.reason == 'backend_error' or ctx.runtime.audit_failed:
            ledger.stop('operational_error')
    except asyncio.CancelledError:
        row['status'] = 'cancelled'
        ledger.stop('cancelled')
        raise
    except Exception as exc:
        row.update(status='error', error_type=type(exc).__name__)
        ledger.stop('operational_error')
    finally:
        errors = []
        for close in ([ctx.runtime.aclose] if ctx is not None else []) + ([channel.aclose] if channel is not None else []):
            try:
                await finish_cleanup(close())
            except (Exception, asyncio.CancelledError) as exc:
                errors.append(type(exc).__name__)
                cleanup_interrupted |= isinstance(exc, asyncio.CancelledError)
        if process is not None:
            if process.returncode is None:
                process.terminate()
            try:
                await finish_cleanup(asyncio.wait_for(process.wait(), 5))
            except TimeoutError:
                process.kill()
                await finish_cleanup(process.wait())
                errors.append('product_termination_timeout')
        if app_log is not None:
            app_log.close()
        if cleanup_interrupted:
            row['status'] = 'cancelled'
            ledger.stop('cancelled')
        row['cleanup_confirmed'] = not errors and (process is None or process.returncode is not None) and (channel is None or channel.closed and (channel.browser is None or not channel.browser.is_connected()))
        row['cleanup_errors'] = errors
        row['database'] = database_state(database)
        http = path / 'http.jsonl'
        row['http'] = [json.loads(line) for line in http.read_text().splitlines()] if http.exists() else []
        row['app_unchanged'] = app_manifest(app_python) == app_before
        row['app_sha256'] = digest(app_before)
        row['usage'] = ctx.budget.snapshot() if ctx is not None else {}
        if 'result' in row:
            row['result']['cleanup'] = 'confirmed' if row['cleanup_confirmed'] else 'unknown'
        row['elapsed_ms'] = (time.monotonic() - started) * 1000
        row['strict_completed'] = bool(row['status'] == 'finished' and row['cleanup_confirmed'] and row['app_unchanged'] and row['elapsed_ms'] <= 120000
            and row.get('result', {}).get('status') == 'completed' and row['database']['records'] == case['oracle']['rows']
            and row['database']['schema'] == initial_schema and len(row['database']['writes']) == case['oracle']['writes']
            and all(w['operation'] == case['oracle']['operation'] for w in row['database']['writes'])
            and sum(r['method'] == 'POST' for r in row['http']) == 1)
        row['recovery_completed'] = bool(case['recovery'] and row['strict_completed']
            and sum(r['status'] == '503 Service Unavailable' for r in row['http']) == 1
            and any(r['method'] == 'GET' and r['query'] == 'retry=1' and r['status'] == '200 OK' for r in row['http']))
        row['capped_completion_ms'] = row['elapsed_ms'] if row['strict_completed'] else 120000
        if not row['cleanup_confirmed']:
            ledger.stop('cleanup_failed')
        if not row['app_unchanged']:
            ledger.stop('operational_error')
        if any(r['status'].startswith('5') and not r['injected'] for r in row['http']):
            ledger.stop('operational_error')
        ledger.finish_trial()
        if own_ledger:
            ledger.close()
        (path / 'row.json').write_text(json.dumps(row, ensure_ascii=False, indent=2) + '\n')
        if cleanup_interrupted:
            raise asyncio.CancelledError
    return row


async def run_batch(output: Path, approved: str, *, jev_credential: str, peer_credential: str) -> dict:
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit
    f = load_freeze(output, approved)
    if not jev_credential.strip() or not peer_credential.strip():
        raise ValueError('both credentials required')
    if any((output / name).exists() for name in ('started.json', 'result.json', 'spend.jsonl')):
        raise FileExistsError('started batch cannot resume')
    (output / 'started.json').write_text(json.dumps({'sha256': approved}) + '\n')
    rows = [{**item, 'status': 'not_run', 'strict_completed': False, 'cleanup_confirmed': False,
             'recovery_completed': False, 'capped_completion_ms': 120000} for item in f['schedule']]
    result = {'sha256': approved, 'rows': rows, 'completed': False}
    ledger = SpendLedger(SpendLimit(0, 0), record_only=True, journal=output / 'spend.jsonl')
    def persist():
        result['spend'] = ledger.snapshot()
        (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    persist()
    try:
        for row in rows:
            load_freeze(output, approved)
            case = next(c for c in f['cases'] if c['id'] == row['case'])
            try:
                row.update(await run_task(case, row['arm'], output, app_python=Path(f['app']['python']),
                    jev_credential=jev_credential, peer_credential=peer_credential, ledger=ledger))
            except asyncio.CancelledError:
                saved = output / row['id'] / 'row.json'
                row.update(json.loads(saved.read_text()) if saved.exists() else {'status': 'cancelled'})
                ledger.stop('cancelled')
                raise
            except Exception as exc:
                row.update(status='error', error_type=type(exc).__name__, cleanup_confirmed=False)
                ledger.stop('operational_error')
            persist()
            if ledger.snapshot()['stop_reason']:
                break
        result['completed'] = not ledger.snapshot()['stop_reason'] and all(r['status'] == 'finished' for r in rows)
    finally:
        ledger.close()
        persist()
    return result


def main() -> None:
    import argparse
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--app-python', type=Path)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--approved-sha256')
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--database', type=Path)
    parser.add_argument('--fault-path')
    args = parser.parse_args()
    if args.serve:
        if not args.database or args.app_python or args.run or args.approved_sha256:
            parser.error('internal server requires only database/output and optional fault path')
        serve_product(args.database, args.output, args.fault_path)
        return
    if args.database or args.fault_path:
        parser.error('database and fault path are internal server options')
    if not args.run:
        if not args.app_python or args.approved_sha256:
            parser.error('preparation requires app Python, no approval digest')
        f = prepare(args.output, app_python=args.app_python)
        print(json.dumps({'sha256': f['sha256'], 'tasks': len(f['schedule']), 'record_only': True}))
        return
    if not args.approved_sha256 or args.app_python:
        parser.error('execution uses the frozen digest only')
    from dotenv import dotenv_values
    values = {**dotenv_values(ROOT / 'core/.env'), **os.environ}
    result = asyncio.run(run_batch(args.output, args.approved_sha256,
        jev_credential=values.get('TYPESAFE_API_KEY') or '', peer_credential=values.get('OPENROUTER_API_KEY') or ''))
    print(json.dumps({'completed': result['completed'], 'stop_reason': result['spend']['stop_reason']}))
    raise SystemExit(0 if result['completed'] else 1)


if __name__ == '__main__':
    main()
