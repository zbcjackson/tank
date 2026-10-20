"""Frozen V/JT migration comparison on the qualified unmodified linkding product."""
from __future__ import annotations

import hashlib
import json
import tarfile
import tomllib
from importlib import metadata
from pathlib import Path

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
                    {'key': f'status:Editor seen:{target}', 'value': 'true'}]}],
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
         'business_evidence': 'actual read-only records/tags projection, current visible list and actual observed editor history; no oracle comparisons in observer',
         'acceptance': 'all bookmarks tables/columns and schema preserved except requested title and increasing target date_modified; one correct POST302 and actual returned list; list order not scored',
         'authentication': 'synthetic session setup before measured Controller actions; elapsed time includes setup and cleanup',
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
