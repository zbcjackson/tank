"""Frozen V/JT migration comparison on the qualified unmodified linkding product."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib
import json
import shutil
import sys
import tarfile
import tomllib
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel

ROOT = Path(__file__).resolve().parents[2]
PROVENANCE = ROOT.parent / 'docs/research/artifacts/jev-second-product-qualification-20261020.tar.gz'
PROVENANCE_SHA256 = 'adecf722acac0673aba12768273545dce0def7f1d731a93eacdfa1c8ac64570c'


def provenance() -> dict:
    if hashlib.sha256(PROVENANCE.read_bytes()).hexdigest() != PROVENANCE_SHA256:
        raise ValueError('qualified product provenance changed')
    with tarfile.open(PROVENANCE) as archive:
        member = archive.extractfile('qualification/task-freeze.json')
        if member is None:
            raise ValueError('qualified task specification missing')
        return json.loads(member.read())


def source_files(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and not
            set(p.relative_to(root).parts) & {'.venv', 'node_modules', 'data', '__pycache__'}
            and p.suffix != '.pyc'}


def app_manifest(app_python: Path) -> dict:
    if not app_python.is_absolute() or not app_python.is_file():
        raise ValueError('absolute qualified product Python required')
    root = app_python.parents[2]
    project = tomllib.loads((root / 'pyproject.toml').read_text())['project']
    if project['name'] != 'linkding' or project['version'] != '1.47.0':
        raise ValueError('qualified linkding 1.47.0 required')
    proof = provenance()
    sources = source_files(root)
    if sources != proof['product']['app_file_sha256']:
        raise ValueError('unmodified qualified product source/build required')
    sites = list((app_python.parent.parent / 'lib').glob('python*/site-packages'))
    if len(sites) != 1:
        raise ValueError('one isolated product site-packages required')
    versions = {d.metadata['Name'].lower(): d.version for d in metadata.distributions(path=[str(sites[0])])}
    expected = {name.lower(): version for name, version in proof['product']['environment']['versions'].items()}
    if versions != expected:
        raise ValueError('qualified product dependency versions required')
    env = app_python.parent.parent
    files = {str(p.relative_to(env)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sites[0].rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    files['pyvenv.cfg'] = hashlib.sha256((env / 'pyvenv.cfg').read_bytes()).hexdigest()
    files['bin/python'] = hashlib.sha256(app_python.read_bytes()).hexdigest()
    return {'root': str(root), 'python': str(app_python), 'source_files': sources,
            'environment_files': files, 'versions': versions, 'provenance_sha256': PROVENANCE_SHA256}


def encoded(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def seed_records() -> list[dict]:
    return [{'id': n, 'url': f'https://example.test/item-{n}', 'title': f'Draft bookmark {n}',
             'description': f'Keep description {n}', 'notes': '', 'unread': False,
             'shared': False, 'is_archived': False, 'owner_id': 1, 'tag_names': ['keep']}
            for n in (1, 2)]


def cases() -> list[dict]:
    result = []
    for target in (1, 2):
        key = f'linkding-title-{target}'
        records = seed_records()
        records[target - 1]['title'] = f'Launch bookmark {target}'
        visible = {'path': '/bookmarks', 'records': [
            {'id': str(r['id']), 'url': r['url'], 'title': r['title'],
             'description': f'keep | {r["description"]}'} for r in records]}
        intent = (f'Find bookmark titled Draft bookmark {target} at https://example.test/item-{target}. '
                  f'Change only its title to Launch bookmark {target}, save, and confirm the returned bookmark list. '
                  'Preserve other fields and records.')
        goal = {'schema_version': 2, 'goal_id': key, 'scope': 'linkding', 'authorization_ref': 'current_task',
                'intent': intent, 'objective': intent, 'allowed_operations': ['click', 'fill'],
                'constraints': ['Do not delete, archive, share or change any other field. Do not execute SQL.'],
                'inputs': [{'key': 'title', 'purpose': 'Requested title', 'field_label': 'Title',
                            'value': f'Launch bookmark {target}'}],
                'outcomes': [{'id': 'requested-editor-observed', 'conditions': [
                    {'key': f'status:Editor seen:https://example.test/item-{target}', 'value': 'true'}]}],
                'completion': [{'key': 'status:Records', 'value': encoded(records)},
                               {'key': 'status:List records', 'value': encoded(visible)}]}
        result.append({'id': key, 'target': target, 'kind': 'update', 'recovery': False, 'workflow': False,
                       'seed': seed_records(), 'start_path': '/bookmarks', 'goal': goal,
                       'oracle': {'rows': records, 'visible_list': visible, 'edit_path': f'/bookmarks/{target}/edit'}})
    return result


def freeze_inputs(app_python: Path) -> dict:
    from benchmarks.computer_use import jev_real_product_route as shared
    from benchmarks.computer_use import jev_vision_route as base
    from benchmarks.computer_use.jev_image_dev import digest
    items = cases()
    f = {'revision': 'linkding-route-1', 'cases': items,
         'schedule': [{'id': c['id'] + '-' + arm, 'case': c['id'], 'arm': arm}
                      for index, c in enumerate(items) for arm in (('v', 'jt') if index == 0 else ('jt', 'v'))],
         'app': app_manifest(app_python), 'source_sha256': {**base.sources(), **{
             str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in (Path(__file__), Path(shared.__file__))}},
         'models': {'jev': base.JEV, 'peer': base.PEER}, 'record_only': True,
         'versions': {n: metadata.version(n) for n in ('playwright', 'openai', 'typesafe-sdk', 'pillow')},
         'seconds_per_task': 120, 'max_actions': 6, 'max_observations': 24, 'retries': 0,
         'scope': 'unmodified qualified linkding; isolated copies and synthetic accounts/bookmarks only',
         'data_policy': {'jev': 'text only', 'peer': 'synthetic PNG plus the same goal/snapshot/candidates',
                         'max_parameter_bytes': 32 * 1024 * 1024},
         'business_evidence': 'actual read-only records/tags projection, current visible list and actual observed editor history; no oracle comparisons in observer',
         'acceptance': 'final values of all bookmarks tables/columns and schema preserved except requested title and increasing target date_modified; one correct POST302 and actual returned list; list order not scored; no claim of one SQL write or title-only SQL columns',
         'authentication': 'synthetic session setup before measured Controller actions; elapsed time includes setup and cleanup',
         'fixture_initialization': 'official authenticated list GET primes lazy defaults before initial DB receipt',
         'provenance_task_spec_sha256': provenance()['sha256'],
         'price_nano_usd': {'jev': [42, 0], 'peer': [825, 4125]},
         'price_evidence': 'historical frozen estimates, not an invoice'}
    f['sha256'] = digest(f)
    return f


def prepare(output: Path, *, app_root: Path) -> dict:
    f = freeze_inputs(app_root / '.venv/bin/python')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'freeze.json').write_text(json.dumps(f, ensure_ascii=False, indent=2) + '\n')
    return f


def load_freeze(output: Path, approved: str) -> dict:
    stored = json.loads((output / 'freeze.json').read_text())
    f = freeze_inputs(Path(stored['app']['python']))
    if stored != f or approved != f['sha256']:
        raise ValueError('linkding route freeze changed')
    return f


_PAGE_READ = r"""() => {
    const visible = node => node && node.getClientRects().length &&
        getComputedStyle(node).visibility !== 'hidden' && !node.closest('[hidden],[aria-hidden="true"]');
    const records = [...document.querySelectorAll('li[data-bookmark-id]')].filter(visible).map(node => {
        const link = node.querySelector('.title a[href]');
        return {id: node.dataset.bookmarkId, title: visible(link) ? link.innerText.trim() : null,
            url: visible(link) ? link.href : null,
            description: node.querySelector('.description')?.innerText.trim() ?? null};
    });
    const route = /^\/bookmarks\/(\d+)\/edit$/.exec(location.pathname);
    const url = document.getElementById('id_url'), title = document.getElementById('id_title');
    return {list: {path: location.pathname, records},
        editor: route && visible(url) && visible(title) ?
            {id: route[1], url: url.value, title: title.value} : null};
}"""


def canonical_list(actual: dict) -> dict:
    return {**actual, 'records': sorted(actual['records'], key=lambda r: r['id'])}


def database_state(database: Path) -> dict:
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'bookmarks_%' ORDER BY name")]
        tables = {name: [dict(r) for r in db.execute('SELECT * FROM ' + name + ' ORDER BY rowid')] for name in names}
        tags = {r['id']: r['name'] for r in tables['bookmarks_tag']}
        records = []
        for row in tables['bookmarks_bookmark']:
            record = {key: row[key] for key in ('id', 'url', 'title', 'description', 'notes', 'owner_id')}
            record.update({key: bool(row[key]) for key in ('unread', 'shared', 'is_archived')})
            record['tag_names'] = sorted(tags[link['tag_id']] for link in tables['bookmarks_bookmark_tags']
                                        if link['bookmark_id'] == row['id'])
            records.append(record)
        return {'records': records, 'tables': tables,
                'schema': [list(r) for r in db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name')]}


def seed_product(app_root: Path, output: Path, seed_file: Path) -> None:
    import os
    sys.path.insert(0, str(app_root))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'bookmarks.settings'
    os.environ['LD_DISABLE_BACKGROUND_TASKS'] = 'true'
    for name in ('assets', 'favicons', 'previews'):
        (app_root / 'data' / name).mkdir(parents=True, exist_ok=True)
    django = importlib.import_module('django')
    django.setup()
    settings = importlib.import_module('django.conf').settings
    User = importlib.import_module('django.contrib.auth.models').User
    call_command = importlib.import_module('django.core.management').call_command
    Client = importlib.import_module('django.test').Client
    Bookmark = importlib.import_module('bookmarks.models').Bookmark
    create_bookmark = importlib.import_module('bookmarks.services.bookmarks').create_bookmark
    call_command('migrate', interactive=False, verbosity=0)
    user = User.objects.create_user(username='qualification-user', password='synthetic-local-only',
                                    email='qualification@example.test')
    for record in json.loads(seed_file.read_text()):
        bookmark = Bookmark(id=record['id'], url=record['url'], title=record['title'],
            description=record['description'], notes=record['notes'], unread=record['unread'],
            shared=record['shared'], is_archived=record['is_archived'], owner=user)
        create_bookmark(bookmark, ' '.join(record['tag_names']), user)
    client = Client()
    client.force_login(user)
    if client.get('/bookmarks').status_code != 200:
        raise RuntimeError('product initial list setup failed')
    cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
    (output / 'auth.json').write_text(json.dumps({'name': settings.SESSION_COOKIE_NAME, 'value': cookie}) + '\n')
    (output / 'database-before.json').write_text(json.dumps(database_state(app_root / 'data/db.sqlite3'), indent=2) + '\n')


def serve_product(app_root: Path, output: Path) -> None:
    import os
    import time
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server
    sys.path.insert(0, str(app_root))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'bookmarks.settings'
    os.environ['LD_DISABLE_BACKGROUND_TASKS'] = 'true'
    StaticFilesHandler = importlib.import_module('django.contrib.staticfiles.handlers').StaticFilesHandler
    get_wsgi_application = importlib.import_module('django.core.wsgi').get_wsgi_application
    application = StaticFilesHandler(get_wsgi_application())
    class Server(ThreadingMixIn, WSGIServer):
        daemon_threads = True
    class Quiet(WSGIRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass
    def middleware(environ, start_response):
        def status_line(status, headers, exc_info=None):
            with (output / 'http.jsonl').open('a') as journal:
                journal.write(json.dumps({'method': environ['REQUEST_METHOD'], 'path': environ['PATH_INFO'],
                    'query': environ.get('QUERY_STRING', ''), 'status': status, 'injected': False,
                    'at_monotonic': time.monotonic()}) + '\n')
            return start_response(status, headers, exc_info)
        return application(environ, status_line)
    (output / 'http.jsonl').touch(exist_ok=False)
    with make_server('127.0.0.1', 0, middleware, server_class=Server, handler_class=Quiet) as server:
        (output / 'ready.json').write_text(json.dumps({'port': server.server_port}) + '\n')
        server.serve_forever()


class LinkdingAdapter:
    def __init__(self, app_python: Path) -> None:
        if not app_python.is_absolute() or not app_python.is_file():
            raise ValueError('absolute qualified product Python required')
        self.root = app_python.parents[2]
        self.expected_source = source_files(self.root)

    def load_freeze(self, output: Path, approved: str) -> dict:
        return load_freeze(output, approved)

    def manifest(self, app_python: Path) -> dict:
        return app_manifest(app_python)

    def database_state(self, database: Path) -> dict:
        return database_state(database)

    async def initialize(self, path: Path, app_python: Path, case: dict) -> Path:
        import os
        from benchmarks.computer_use import jev_real_product_route as shared
        trial = path / 'app'
        def copy_source():
            trial.mkdir(exist_ok=False)
            for name in self.expected_source:
                target = trial / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.root / name, target)
        if await shared.settle_cleanup(asyncio.to_thread(copy_source)):
            raise asyncio.CancelledError
        seed = path / 'seed-input.json'
        seed.write_text(json.dumps(case['seed']) + '\n')
        with (path / 'seed.log').open('wb') as log:
            process = await asyncio.create_subprocess_exec(str(app_python), str(Path(__file__)), '--seed',
                '--app-root', str(trial), '--output', str(path), '--seed-file', str(seed), cwd=trial,
                env={'PATH': os.environ.get('PATH', ''), 'PYTHONUNBUFFERED': '1'}, stdout=log, stderr=asyncio.subprocess.STDOUT)
            try:
                await asyncio.wait_for(process.wait(), 10)
            finally:
                if process.returncode is None:
                    process.terminate()
                if await shared.settle_cleanup(process.wait()):
                    raise asyncio.CancelledError
            if process.returncode != 0:
                raise RuntimeError('linkding fixture initialization failed')
        return trial / 'data/db.sqlite3'

    def server_command(self, app_python: Path, database: Path, output: Path) -> tuple[str, ...]:
        return (str(app_python), str(Path(__file__)), '--serve', '--app-root', str(database.parent.parent),
                '--output', str(output))

    def server_directory(self, database: Path, output: Path) -> Path:
        return database.parent.parent

    def channel(self, config: BrowserConfig, database: Path, row: dict) -> ManagedChromiumChannel:
        from dataclasses import replace
        from agent_computer_use.channels.dom import ManagedChromiumChannel
        from agent_computer_use.contracts import Fact
        row['database_path'] = str(database)
        row['database_before'] = json.loads((database.parents[2] / 'database-before.json').read_text())
        row['product_observations'] = []
        class Channel(ManagedChromiumChannel):
            authenticated = False
            async def start(self, context):
                await super().start(context)
                if not self.authenticated:
                    self.check(context)
                    assert self.page is not None
                    auth = json.loads((database.parents[2] / 'auth.json').read_text())
                    await self.page.context.add_cookies([{'name': auth['name'], 'value': auth['value'],
                                                         'url': self.config.url}])
                    await self.page.goto(self.config.url, timeout=5000)
                    self.check(context)
                    self.authenticated = True
            async def observe(self, scope, context):
                snapshot = await super().observe(scope, context)
                actual = await asyncio.to_thread(database_state, database)
                self.check(context)
                assert self.page is not None
                page = await self.page.evaluate(_PAGE_READ)
                self.check(context)
                editor = page['editor']
                if editor is not None:
                    seen.add(editor['url'])
                row['product_observations'].append({'observation_id': snapshot.observation_id,
                    'list': page['list'], 'records': actual['records'], 'editor': editor,
                    'seen_editor_urls': sorted(seen)})
                self.previous = replace(snapshot, facts=(*snapshot.facts,
                    Fact(key='status:Records', value=encoded(actual['records'])),
                    Fact(key='status:List records', value=encoded(canonical_list(page['list']))),
                    *(Fact(key=f'status:Editor seen:{identity}', value='true') for identity in sorted(seen))))
                return self.previous
        seen: set[str] = set()
        return Channel(config)

    async def readback(self, channel: ManagedChromiumChannel, row: dict) -> None:
        assert channel.page is not None
        row['list_readback'] = (await channel.page.evaluate(_PAGE_READ))['list']
        row['trial_source_unchanged'] = await asyncio.to_thread(
            lambda: source_files(Path(row['database_path']).parent.parent) == self.expected_source)

    def accepted(self, row: dict, case: dict, initial_schema: list) -> bool:
        actual, before = row['database'], row['database_before']
        if (actual['records'] != case['oracle']['rows'] or actual['schema'] != initial_schema
                or not row.get('trial_source_unchanged')
                or canonical_list(row['list_readback']) != case['oracle']['visible_list']):
            return False
        expected = copy.deepcopy(before['tables'])
        target = next(r for r in expected['bookmarks_bookmark'] if r['id'] == case['target'])
        after = next(r for r in actual['tables']['bookmarks_bookmark'] if r['id'] == case['target'])
        if after['date_modified'] <= target['date_modified']:
            return False
        target['title'] = after['title']
        target['date_modified'] = after['date_modified']
        if expected != actual['tables']:
            return False
        posts = [(i, h) for i, h in enumerate(row['http']) if h['method'] == 'POST']
        lists = [i for i, h in enumerate(row['http']) if h['method'] == 'GET' and h['path'] == '/bookmarks' and h['status'] == '200 OK']
        edits = [i for i, h in enumerate(row['http']) if h['method'] == 'GET' and h['path'] == case['oracle']['edit_path'] and h['status'] == '200 OK']
        return bool(len(posts) == 1 and posts[0][1]['path'] == case['oracle']['edit_path']
            and posts[0][1]['status'] == '302 Found'
            and any(i < j < posts[0][0] for i in lists for j in edits) and any(i > posts[0][0] for i in lists)
            and any(o['editor'] is not None and o['editor']['id'] == str(case['target'])
                    and o['editor']['url'] == case['seed'][case['target'] - 1]['url']
                    for o in row['product_observations']))


async def run_task(case: dict, arm: str, output: Path, *, app_python: Path,
                   jev_credential: str, peer_credential: str, ledger=None) -> dict:
    from benchmarks.computer_use import jev_real_product_route as shared
    return await shared.run_task(case, arm, output, app_python=app_python, jev_credential=jev_credential,
        peer_credential=peer_credential, ledger=ledger, adapter=LinkdingAdapter(app_python))


async def run_batch(output: Path, approved: str, *, jev_credential: str, peer_credential: str) -> dict:
    from benchmarks.computer_use import jev_real_product_route as shared
    frozen = load_freeze(output, approved)
    return await shared.run_batch(output, approved, jev_credential=jev_credential, peer_credential=peer_credential,
        adapter=LinkdingAdapter(Path(frozen['app']['python'])))


def main() -> None:
    import argparse
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--seed', action='store_true')
    mode.add_argument('--serve', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--app-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed-file', type=Path)
    parser.add_argument('--approved-sha256')
    args = parser.parse_args()
    if args.seed or args.serve:
        if args.app_root is None or args.approved_sha256:
            parser.error('internal fixture modes require app root, no approval digest')
        if args.seed and args.seed_file is None:
            parser.error('fixture seed requires input file')
        if args.serve and args.seed_file:
            parser.error('server does not accept seed input')
        if args.seed and args.seed_file is not None:
            seed_product(args.app_root, args.output, args.seed_file)
        else:
            serve_product(args.app_root, args.output)
        return
    if args.seed_file:
        parser.error('seed input is only for internal initialization')
    if not args.run:
        if args.app_root is None or args.approved_sha256:
            parser.error('preparation requires app root, no approval digest')
        frozen = prepare(args.output, app_root=args.app_root)
        print(json.dumps({'sha256': frozen['sha256'], 'tasks': len(frozen['schedule']), 'record_only': True}))
        return
    if not args.approved_sha256 or args.app_root:
        parser.error('execution uses only the approved executable freeze')
    load_freeze(args.output, args.approved_sha256)
    from dotenv import dotenv_values
    values = {**dotenv_values(ROOT / 'core/.env'), **os.environ}
    result = asyncio.run(run_batch(args.output, args.approved_sha256,
        jev_credential=values.get('TYPESAFE_API_KEY') or '', peer_credential=values.get('OPENROUTER_API_KEY') or ''))
    print(json.dumps({'completed': result['completed'], 'stop_reason': result['spend']['stop_reason']}))
    raise SystemExit(0 if result['completed'] else 1)


if __name__ == '__main__':
    main()
