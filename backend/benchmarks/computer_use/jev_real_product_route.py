"""Frozen V/JT development comparison on an unmodified sqlite-web installation."""
from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from contextlib import closing
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel
    from agent_computer_use.contracts import Action, Binding, DispatchReceipt
    from tank_backend.agents.subagent import SubAgentContext


class ProductAdapter(Protocol):
    def load_freeze(self, output: Path, approved: str) -> dict: ...
    def manifest(self, app_python: Path) -> dict: ...
    async def initialize(self, path: Path, app_python: Path, case: dict) -> Path: ...
    def server_command(self, app_python: Path, database: Path, output: Path) -> tuple[str, ...]: ...
    def server_directory(self, database: Path, output: Path) -> Path: ...
    def channel(self, config: BrowserConfig, database: Path, row: dict) -> ManagedChromiumChannel: ...
    async def readback(self, channel: ManagedChromiumChannel, row: dict) -> None: ...
    def database_state(self, database: Path) -> dict: ...
    def accepted(self, row: dict, case: dict, initial_schema: list) -> bool: ...

ROOT = Path(__file__).resolve().parents[2]


async def settle_cleanup(operation: Awaitable[object]) -> bool:
    pending = asyncio.ensure_future(operation)
    interrupted = False
    while True:
        try:
            await asyncio.shield(pending)
            return interrupted
        except asyncio.CancelledError:
            if pending.cancelled():
                raise
            interrupted = True


def backup_database(database: Path, output: Path) -> None:
    import sqlite3
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as source:
        with closing(sqlite3.connect(output)) as target:
            source.backup(target)


_LIST_READ = """() => {
    const visible = node => node && node.getClientRects().length && getComputedStyle(node).visibility !== 'hidden';
    const table = document.querySelector('table.cell-content');
    const columns = table ? [...table.querySelectorAll('thead th')].map((node, index) =>
        ({index, name: node.getAttribute('data-col'), visible: visible(node)})).filter(c => c.name && c.visible) : [];
    const rows = table ? [...table.querySelectorAll('tbody tr')].filter(visible).map(row =>
        columns.map(c => visible(row.cells[c.index]) ? row.cells[c.index].innerText.trim() : null)) : [];
    return {path: location.pathname, columns: columns.map(c => c.name), rows};
}"""


def encoded(records: list[dict] | dict) -> str:
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


def workflow_cases() -> list[dict]:
    result = []
    for recovery in (False, True):
        for case in cases():
            if case['kind'] != 'update' or case['recovery']:
                continue
            key = f'workflow-update-{case["order"]}-' + ('recovery' if recovery else 'normal')
            target = case['order'] + 1
            old = next(r for r in case['seed'] if r['id'] == target)
            new = next(r for r in case['oracle']['rows'] if r['id'] == target)
            intent = (f'Starting from the work_items list, find record id {target} with title {old["title"]!r}. '
                      f'Change its title to {new["title"]!r}. Keep its notes and all other records unchanged. '
                      'Confirm the updated record and unchanged records on the returned list.')
            visible = {'path': '/work_items/content/', 'columns': ['id', 'title', 'notes'],
                       'rows': [[str(r[k]) for k in ('id', 'title', 'notes')] for r in case['oracle']['rows']]}
            goal = {**case['goal'], 'goal_id': 'goal-' + hashlib.sha256(key.encode()).hexdigest()[:16],
                    'intent': intent, 'objective': intent,
                    'outcomes': [{'id': 'correct-record-editor', 'conditions': [{'key': f'status:Editor seen:{target}', 'value': 'true'}]}],
                    'completion': [*case['goal']['completion'], {'key': 'status:List rows', 'value': encoded(visible)}]}
            result.append({**case, 'id': key, 'workflow': True, 'recovery': recovery,
                           'start_path': '/work_items/content/', 'fault_path': case['start_path'] if recovery else None,
                           'goal': goal, 'oracle': {**case['oracle'], 'visible_list': visible, 'edit_path': case['start_path']}})
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


def freeze_inputs(app_python: Path, *, workflow: bool = False) -> dict:
    from benchmarks.computer_use import jev_vision_route as base
    from benchmarks.computer_use.jev_image_dev import digest
    items = workflow_cases() if workflow else cases()
    f = {'revision': 'real-product-workflow-1' if workflow else 'real-product-1', 'workflow': workflow, 'cases': items,
         'schedule': [{'id': c['id'] + '-' + arm, 'case': c['id'], 'arm': arm}
                      for c in items for arm in (('v', 'jt') if (c['order'] + (c['kind'] == 'update')) % 2 == 0 else ('jt', 'v'))],
         'app': app_manifest(app_python), 'source_sha256': {**base.sources(),
             str(Path(__file__).relative_to(ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
         'models': {'jev': base.JEV, 'peer': base.PEER}, 'record_only': True,
         'versions': {n: metadata.version(n) for n in ('playwright', 'openai', 'typesafe-sdk', 'pillow')},
         'seconds_per_task': 120, 'max_actions': 6, 'max_observations': 24, 'retries': 0,
         'scope': 'unmodified local sqlite-web; synthetic records only; Jev text and Gemini PNG+text',
         'business_evidence': ('read-only actual work_items rows plus actual visible list cells/path, no oracle in observer' if workflow else
                               'read-only actual work_items rows, no expected-data comparison in observer'),
         'recovery': ('first edit GET returns injected 503; list starts, Retry only GET; actual list readback required' if workflow else
                      'first form GET returns injected 503 without forwarding; Retry adds retry=1; no POST retry; direct form starts in both conditions'),
         'price_nano_usd': {'jev': [42, 0], 'peer': [825, 4125]},
         'price_evidence': 'historical frozen estimate, not an invoice'}
    f['sha256'] = digest(f)
    return f


def prepare(output: Path, *, app_python: Path, workflow: bool = False) -> dict:
    f = freeze_inputs(app_python, workflow=workflow)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'freeze.json').write_text(json.dumps(f, ensure_ascii=False, indent=2) + '\n')
    return f


def load_freeze(output: Path, approved: str) -> dict:
    stored = json.loads((output / 'freeze.json').read_text())
    f = freeze_inputs(Path(stored['app']['python']), workflow=stored.get('workflow', False))
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
                   jev_credential: str, peer_credential: str, ledger=None,
                   adapter: ProductAdapter | None = None, max_candidates: int = 32,
                   prewarm_path: str | None = None,
                   before_dispatch: Callable[[dict, ManagedChromiumChannel, Action, SubAgentContext], Awaitable[None]] | None = None) -> dict:
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
    manifest = app_manifest if adapter is None else adapter.manifest
    read_database = database_state if adapter is None else adapter.database_state
    app_before = manifest(app_python)
    own_ledger = ledger is None
    if ledger is None:
        ledger = SpendLedger(SpendLimit(0, 0), record_only=True, journal=path / 'spend.jsonl')
    ledger.start_trial(row_id, SpendLimit(0, 0))
    row = {'id': row_id, 'case': case['id'], 'task_id': task_id, 'arm': arm, 'kind': case['kind'],
           'recovery': case['recovery'], 'workflow': bool(case.get('workflow')), 'status': 'started', 'strict_completed': False,
           'recovery_completed': False, 'cleanup_confirmed': False, 'events': [], 'calls': []}
    database = path / 'fixture.db'
    initial_schema: list | None = None
    process = channel = ctx = None
    app_log = None
    seen_editors: set[str] = set()
    if case.get('workflow'):
        row['workflow_observations'] = []
    class ProductChannel(ManagedChromiumChannel):
        async def observe(self, scope, context):
            snapshot = await super().observe(scope, context)
            if not snapshot.ready or not snapshot.complete:
                return snapshot
            actual = await asyncio.to_thread(database_state, database)
            self.check(context)
            if not await self.is_snapshot_current(snapshot, context):
                return self.unavailable_snapshot(scope)
            self.previous = replace(snapshot, facts=(*snapshot.facts, Fact(key='status:Records', value=encoded(actual['records']))))
            if case.get('workflow'):
                context.check('desktop')
                assert self.page is not None
                visible = await self.page.evaluate(_LIST_READ)
                editor = self.page.get_by_role('textbox', name='id', exact=True)
                editor_id = await editor.input_value() if await editor.count() == 1 and await editor.is_visible() else ''
                context.check('desktop')
                if not await self.is_snapshot_current(self.previous, context):
                    return self.unavailable_snapshot(scope)
                if editor_id:
                    seen_editors.add(editor_id)
                row['workflow_observations'].append({'observation_id': snapshot.observation_id,
                    'list': visible, 'editor_id': editor_id, 'seen_editors': sorted(seen_editors)})
                self.previous = replace(self.previous, facts=(*self.previous.facts,
                    Fact(key='status:List rows', value=encoded(visible)),
                    *(Fact(key=f'status:Editor seen:{identity}', value='true') for identity in sorted(seen_editors))))
            return self.previous
    class Observer:
        def on_event(self, kind, metadata):
            row['events'].append({'kind': kind, **metadata})
    class GuardedExecutor:
        def witness(self, phase: str, binding: Binding, action: Action, **details) -> None:
            with (path / 'dispatch-witness.jsonl').open('a') as journal:
                journal.write(json.dumps({'phase': phase, 'binding': asdict(binding),
                    'action': asdict(action), **details}) + '\n')

        async def is_current(self, binding: Binding, action: Action, context: SubAgentContext) -> bool:
            assert channel is not None
            current = await channel.is_current(binding, action, context)
            self.witness('current', binding, action, current=current)
            return current

        async def dispatch(self, binding: Binding, action: Action, context: SubAgentContext) -> DispatchReceipt:
            assert channel is not None
            try:
                if before_dispatch is not None:
                    await before_dispatch(row, channel, action, context)
                context.check('desktop')
            except (Exception, asyncio.CancelledError) as error:
                self.witness('blocked', binding, action, native_called=False,
                             authorization_active=context.authorization.active,
                             error_type=type(error).__name__)
                raise
            self.witness('authorized', binding, action,
                         authorization_active=context.authorization.active)
            try:
                receipt = await channel.dispatch(binding, action, context)
            except (Exception, asyncio.CancelledError) as error:
                self.witness('error', binding, action, native_called=True,
                             error_type=type(error).__name__)
                raise
            self.witness('returned', binding, action, native_called=True, status=receipt.status)
            return receipt
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
        cleanup_interrupted |= await settle_cleanup(operation)
    try:
        app_log = (path / 'app.log').open('wb')
        if adapter is None:
            create_database(database, case['seed'])
        else:
            database = await adapter.initialize(path, app_python, case)
        initial_schema = read_database(database)['schema']
        await finish_cleanup(asyncio.to_thread(backup_database, database, path / 'before.db'))
        if cleanup_interrupted:
            raise asyncio.CancelledError
        fault_path = case.get('fault_path', case['start_path']) if case['recovery'] else None
        command = ((str(app_python), str(Path(__file__)), '--serve', '--database', str(database),
                    '--output', str(path), *(['--fault-path', fault_path] if fault_path else []))
                   if adapter is None else adapter.server_command(app_python, database, path))
        process = await asyncio.create_subprocess_exec(*command,
            stdout=app_log, stderr=asyncio.subprocess.STDOUT,
            cwd=path if adapter is None else adapter.server_directory(database, path),
            env={'PATH': os.environ.get('PATH', ''), 'PYTHONUNBUFFERED': '1'})
        async with asyncio.timeout(10):
            while not (path / 'ready.json').exists():
                if process.returncode is not None:
                    raise RuntimeError('product process exited before ready')
                await asyncio.sleep(.02)
        port = json.loads((path / 'ready.json').read_text())['port']
        row['prewarm'] = None
        if prewarm_path is not None:
            def prewarm() -> dict:
                import http.client
                warm_started = time.monotonic()
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                try:
                    connection.request('GET', prewarm_path)
                    response = connection.getresponse()
                    response.read()
                    if not 200 <= response.status < 400:
                        raise RuntimeError('product prewarm failed')
                    return {'path': prewarm_path, 'status': response.status,
                            'elapsed_ms': (time.monotonic() - warm_started) * 1000}
                finally:
                    connection.close()
            warming = asyncio.create_task(asyncio.to_thread(prewarm))
            await finish_cleanup(warming)
            row['prewarm'] = warming.result()
            if cleanup_interrupted:
                raise asyncio.CancelledError
        config = BrowserConfig(scope=case['goal']['scope'], url=f'http://127.0.0.1:{port}' + case['start_path'])
        channel = ProductChannel(config) if adapter is None else adapter.channel(config, database, row)
        selector = base.VisionBaseline(channel) if arm == 'v' else VisualSelector(channel)
        executor = GuardedExecutor()
        host = ComputerUseController(channel, executor, selector=selector, max_candidates=max_candidates)
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
            (path / 'final.html').write_text(await channel.page.content(), encoding='utf-8')
            if case.get('workflow'):
                row['list_readback'] = await channel.page.evaluate(_LIST_READ)
            if adapter is not None:
                await adapter.readback(channel, row)
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
        if database.is_file():
            try:
                await finish_cleanup(asyncio.to_thread(backup_database, database, path / 'after.db'))
            except asyncio.CancelledError:
                cleanup_interrupted = True
            except Exception as exc:
                row.update(status='error', evidence_error_type=type(exc).__name__)
                ledger.stop('operational_error')
        if cleanup_interrupted:
            row['status'] = 'cancelled'
            ledger.stop('cancelled')
        row['cleanup_confirmed'] = not errors and (process is None or process.returncode is not None) and (channel is None or channel.closed and (channel.browser is None or not channel.browser.is_connected()))
        row['cleanup_errors'] = errors
        actual = read_database(database) if database.is_file() else None
        row['database'] = actual
        http = path / 'http.jsonl'
        row['http'] = [json.loads(line) for line in http.read_text().splitlines()] if http.exists() else []
        row['app_unchanged'] = manifest(app_python) == app_before
        row['app_sha256'] = digest(app_before)
        row['usage'] = ctx.budget.snapshot() if ctx is not None else {}
        if 'result' in row:
            row['result']['cleanup'] = 'confirmed' if row['cleanup_confirmed'] else 'unknown'
        (path / 'events.json').write_text(json.dumps(row['events']) + '\n')
        (path / 'cleanup-proof.json').write_text(json.dumps({
            'process_pid': process.pid if process is not None else None,
            'process_returncode': process.returncode if process is not None else None,
            'channel_closed': channel.closed if channel is not None else False,
            'browser_closed': bool(channel is not None and
                                   (channel.browser is None or not channel.browser.is_connected())),
            'audit_failed': ctx.runtime.audit_failed if ctx is not None else True,
            'cleanup_errors': errors,
            'files': {name: hashlib.sha256((path / name).read_bytes()).hexdigest()
                      if (path / name).is_file() else None for name in (
                          'before.db', 'after.db', 'audit.jsonl', 'dispatch-witness.jsonl',
                          'events.json', 'final.html', 'http.jsonl', 'calls.jsonl')},
            'elapsed_ms': (time.monotonic() - started) * 1000}) + '\n')
        row['elapsed_ms'] = (time.monotonic() - started) * 1000
        execution_completed = bool(row['status'] == 'finished' and row['cleanup_confirmed'] and row['app_unchanged']
            and row['elapsed_ms'] <= 120000 and row.get('result', {}).get('status') == 'completed')
        if adapter is None:
            row['strict_completed'] = bool(execution_completed and actual is not None and actual['records'] == case['oracle']['rows']
                and actual['schema'] == initial_schema and len(actual['writes']) == case['oracle']['writes']
                and all(w['operation'] == case['oracle']['operation'] for w in actual['writes'])
                and sum(r['method'] == 'POST' for r in row['http']) == 1)
        else:
            row['strict_completed'] = bool(execution_completed and actual is not None and initial_schema is not None
                and adapter.accepted(row, case, initial_schema))
        if case.get('workflow'):
            posts = [(i, h) for i, h in enumerate(row['http']) if h['method'] == 'POST']
            lists = [i for i, h in enumerate(row['http']) if h['method'] == 'GET' and h['status'] == '200 OK' and h['path'] == '/work_items/content/']
            edits = [i for i, h in enumerate(row['http']) if h['method'] == 'GET' and h['status'] == '200 OK' and h['path'] == case['oracle']['edit_path']]
            row['workflow_completed'] = bool(row['strict_completed'] and row.get('list_readback') == case['oracle']['visible_list']
                and any(o['editor_id'] == str(case['order'] + 1) and o['list']['path'] == case['oracle']['edit_path']
                        for o in row.get('workflow_observations', []))
                and len(posts) == 1 and posts[0][1]['path'] == case['oracle']['edit_path']
                and any(i < j < posts[0][0] for i in lists for j in edits) and any(i > posts[0][0] for i in lists))
            row['strict_completed'] = row['workflow_completed']
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


async def run_batch(output: Path, approved: str, *, jev_credential: str, peer_credential: str,
                    adapter: ProductAdapter | None = None) -> dict:
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit
    loader = load_freeze if adapter is None else adapter.load_freeze
    f = loader(output, approved)
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
            loader(output, approved)
            case = next(c for c in f['cases'] if c['id'] == row['case'])
            try:
                if adapter is None:
                    trial = run_task(case, row['arm'], output, app_python=Path(f['app']['python']),
                        jev_credential=jev_credential, peer_credential=peer_credential, ledger=ledger)
                else:
                    trial = run_task(case, row['arm'], output, app_python=Path(f['app']['python']),
                        jev_credential=jev_credential, peer_credential=peer_credential, ledger=ledger, adapter=adapter)
                row.update(await trial)
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
    parser.add_argument('--workflow', action='store_true')
    parser.add_argument('--approved-sha256')
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--database', type=Path)
    parser.add_argument('--fault-path')
    args = parser.parse_args()
    if args.serve:
        if not args.database or args.app_python or args.run or args.approved_sha256 or args.workflow:
            parser.error('internal server requires only database/output and optional fault path')
        serve_product(args.database, args.output, args.fault_path)
        return
    if args.database or args.fault_path:
        parser.error('database and fault path are internal server options')
    if not args.run:
        if not args.app_python or args.approved_sha256:
            parser.error('preparation requires app Python, no approval digest')
        f = prepare(args.output, app_python=args.app_python, workflow=args.workflow)
        print(json.dumps({'sha256': f['sha256'], 'tasks': len(f['schedule']), 'record_only': True}))
        return
    if not args.approved_sha256 or args.app_python or args.workflow:
        parser.error('execution uses the frozen digest only')
    from dotenv import dotenv_values
    values = {**dotenv_values(ROOT / 'core/.env'), **os.environ}
    result = asyncio.run(run_batch(args.output, args.approved_sha256,
        jev_credential=values.get('TYPESAFE_API_KEY') or '', peer_credential=values.get('OPENROUTER_API_KEY') or ''))
    print(json.dumps({'completed': result['completed'], 'stop_reason': result['spend']['stop_reason']}))
    raise SystemExit(0 if result['completed'] else 1)


if __name__ == '__main__':
    main()
