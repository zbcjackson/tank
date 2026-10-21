"""Reviewed-spec calibration on two original products; never a confirmation sample."""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import tarfile
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel
    from agent_computer_use.contracts import Action
    from tank_backend.agents.subagent import SubAgentContext

from benchmarks.computer_use import jev_linkding_route as link
from benchmarks.computer_use import jev_real_product_route as shared
from benchmarks.computer_use import jev_vision_route as base
from benchmarks.computer_use.jev_image_dev import digest

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT.parent / 'docs/research/artifacts'
INPUTS = 'jev-confirmation-preparation-20261021.tar.gz'
INPUTS_SHA = '9af2212aba1f931fdfbcb1ba4f4a262eb7a434eb4eb1183bb1f01ed4507a3ae0'
REVIEW = 'jev-confirmation-preparation-review-20261021.tar.gz'
REVIEW_SHA = '855182c90243b2a2ed0d3d2e09cdc73ab1802915513441f0faf4c640e1ab910f'
SQL_PROOF = 'jev-product-list-workflow-20261020.tar.gz'
SQL_PROOF_SHA = 'ba175ce8ca009c5c15ddf09316a05fdb7a7e9e01aa9ed88bc11eb2bfc6833269'


def members(name: str, expected: str, paths: tuple[str, ...]) -> list[dict | list]:
    data = (ARTIFACTS / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('reviewed provenance changed')
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        values = []
        for path in paths:
            member = archive.extractfile(path)
            if member is None:
                raise ValueError('reviewed specification missing')
            values.append(json.loads(member.read()))
        return values


def canonical_sql_list(value: dict) -> dict:
    return {**value, 'rows': sorted(value['rows'])}


def calibration_cases() -> list[dict]:
    declared = members(INPUTS, INPUTS_SHA, ('v5/calibration-tasks.json',))[0]
    if not isinstance(declared, list) or len(declared) != 24:
        raise ValueError('24 reviewed cases required')
    result = []
    for original in sorted(declared, key=lambda c: hashlib.sha256(c['id'].encode()).hexdigest()):
        for condition in ('cold', 'prewarmed'):
            case = copy.deepcopy(original)
            case['cluster_id'] = case['id']
            case['id'] += '-' + condition
            case['condition'] = condition
            case['negative'] = case['family'] if case['group'] == 'negative' else None
            case['kind'], case['recovery'], case['workflow'] = 'update', case['group'] == 'recovery', False
            wanted = copy.deepcopy(sorted(case['seed'], key=lambda r: r['id']))
            for row in wanted:
                if row['id'] == case['target']:
                    row['title'] = case['public_goal']['inputs'][0]['value']
            if case['product'] == 'linkding':
                case['start_path'] = '/bookmarks'
                edit = f'/bookmarks/{case["target"]}/edit'
                visible = {'path': '/bookmarks', 'records': [
                    {'id': str(r['id']), 'url': r['url'], 'title': r['title'],
                     'description': 'keep | ' + r['description']} for r in wanted]}
                list_key = 'status:List records'
            else:
                case['start_path'] = '/work_items/content/'
                token = base64.urlsafe_b64encode(f'[{case["target"]}]'.encode()).decode().rstrip('=')
                edit = f'/work_items/update/{token}/'
                visible = {'path': case['start_path'], 'columns': ['id', 'title', 'notes'],
                           'rows': [[str(r[k]) for k in ('id', 'title', 'notes')] for r in wanted]}
                list_key = 'status:List rows'
            case['goal'] = {**case.pop('public_goal'), 'goal_id': case['id'], 'completion': [
                {'key': 'status:Records', 'value': link.encoded(wanted)},
                {'key': list_key, 'value': link.encoded(visible)}]}
            case['fault_path'] = (case['start_path'] if case['fault_stage'] == 'list' else edit) if case['recovery'] else None
            case['oracle'] = {'rows': wanted, 'visible_list': visible, 'edit_path': edit,
                              'operation': 'update', 'writes': 1}
            result.append(case)
    return result


def freeze_inputs(sql_python: Path, link_root: Path) -> dict:
    review = members(REVIEW, REVIEW_SHA, ('review/protocol-addendum.json',))[0]
    proof = members(SQL_PROOF, SQL_PROOF_SHA, ('live/freeze.json',))[0]
    if not isinstance(review, dict) or not isinstance(proof, dict):
        raise ValueError('reviewed protocol required')
    sql_app = shared.app_manifest(sql_python)
    if sql_app != proof['app']:
        raise ValueError('unmodified qualified sqlite-web required')
    cases = calibration_cases()
    schedule = []
    for index in range(0, len(cases), 2):
        for offset in (0, 1):
            case = cases[index + offset]
            order = ('v', 'jt') if (index // 2 + offset) % 2 == 0 else ('jt', 'v')
            schedule.extend({'id': case['id'] + '-' + arm, 'case': case['id'], 'arm': arm,
                             'cluster_id': case['cluster_id'], 'condition': case['condition'],
                             'product': case['product'], 'group': case['group']} for arm in order)
    frozen = {'revision': 'two-product-calibration-1', 'formal_confirmation': False,
              'requires_review': True, 'cases': cases, 'schedule': schedule,
              'apps': {'sqlite-web': sql_app, 'linkding': link.app_manifest(link_root / '.venv/bin/python')},
              'source_sha256': {**base.sources(), **{str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (Path(__file__), Path(shared.__file__), Path(link.__file__))}},
              'provenance': {INPUTS: INPUTS_SHA, REVIEW: REVIEW_SHA, SQL_PROOF: SQL_PROOF_SHA},
              'gates': review['gates'], 'sample_size_rule': review['sample_size_rule'],
              'models': {'jev': base.JEV, 'peer': base.PEER}, 'record_only': True,
              'versions': {name: metadata.version(name) for name in ('playwright', 'openai', 'typesafe-sdk', 'pillow')},
              'seconds_per_task': 120, 'max_actions': 6, 'max_observations': 24,
              'max_candidates': 64, 'retries': 0, 'max_parameter_bytes': 32 * 1024 * 1024,
              'data_policy': {'jev': 'text only', 'peer': 'synthetic PNG plus identical goal/snapshot/candidates'},
              'amendments': ['explicit existing64 candidate budget in both arms; browser default32 unchanged',
                  'complete actual current list plus records and editor history; target by identity',
                  'counterbalance initial arm by cluster parity and reverse across start conditions',
                  'full timer includes setup/prewarm/cleanup; provider cache not controlled',
                  'linkding fault applies to first session-bearing matching GET; authentication setup excluded'],
              'price_nano_usd': {'jev': [42, 0], 'peer': [825, 4125]},
              'price_evidence': 'historical frozen estimate, not current price or invoice'}
    frozen['sha256'] = digest(frozen)
    return frozen


def prepare(output: Path, *, sql_python: Path, link_root: Path) -> dict:
    frozen = freeze_inputs(sql_python, link_root)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'freeze.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + '\n')
    return frozen


def load_freeze(output: Path, approved: str) -> dict:
    stored = json.loads((output / 'freeze.json').read_text())
    actual = freeze_inputs(Path(stored['apps']['sqlite-web']['python']), Path(stored['apps']['linkding']['root']))
    if stored != actual or approved != actual['sha256']:
        raise ValueError('calibration freeze changed')
    return actual


class SQLiteAdapter:
    def __init__(self, fault_path: str | None = None) -> None:
        self.fault_path = fault_path

    def load_freeze(self, output: Path, approved: str) -> dict:
        return load_freeze(output, approved)

    def manifest(self, app_python: Path) -> dict:
        return shared.app_manifest(app_python)

    async def initialize(self, path: Path, app_python: Path, case: dict) -> Path:
        import asyncio
        database = path / 'fixture.db'
        if await shared.settle_cleanup(asyncio.to_thread(shared.create_database, database, case['seed'])):
            raise asyncio.CancelledError
        return database

    def server_command(self, app_python: Path, database: Path, output: Path) -> tuple[str, ...]:
        return (str(app_python), str(Path(shared.__file__)), '--serve', '--database', str(database),
                '--output', str(output), *(['--fault-path', self.fault_path] if self.fault_path else []))

    def server_directory(self, database: Path, output: Path) -> Path:
        return output

    def database_state(self, database: Path) -> dict:
        return shared.database_state(database)

    def channel(self, config: BrowserConfig, database: Path, row: dict) -> ManagedChromiumChannel:
        import asyncio
        from dataclasses import replace
        from agent_computer_use.channels.dom import ManagedChromiumChannel
        from agent_computer_use.contracts import Fact
        row['database_before'] = shared.database_state(database)
        row['product_observations'] = []
        seen: set[str] = set()
        class Channel(ManagedChromiumChannel):
            async def observe(self, scope, context):
                snapshot = await super().observe(scope, context)
                if not snapshot.ready or not snapshot.complete:
                    return snapshot
                navigation = self.observed_navigation
                actual = await asyncio.to_thread(shared.database_state, database)
                self.check(context)
                assert self.page is not None
                visible = await self.page.evaluate(shared._LIST_READ)
                identity = self.page.get_by_role('textbox', name='id', exact=True)
                editor_id = await identity.input_value() if await identity.count() == 1 and await identity.is_visible() else ''
                self.check(context)
                if navigation != self.navigation:
                    return self.unavailable_snapshot(scope)
                if editor_id:
                    seen.add(editor_id)
                row['product_observations'].append({'observation_id': snapshot.observation_id,
                    'records': actual['records'], 'list': visible, 'editor_id': editor_id,
                    'seen_editors': sorted(seen)})
                self.previous = replace(snapshot, facts=(*snapshot.facts,
                    Fact(key='status:Records', value=link.encoded(actual['records'])),
                    Fact(key='status:List rows', value=link.encoded(canonical_sql_list(visible))),
                    *(Fact(key=f'status:Editor seen:{value}', value='true') for value in sorted(seen))))
                return self.previous
        return Channel(config)

    async def readback(self, channel: ManagedChromiumChannel, row: dict) -> None:
        assert channel.page is not None
        row['list_readback'] = await channel.page.evaluate(shared._LIST_READ)

    def accepted(self, row: dict, case: dict, initial_schema: list) -> bool:
        actual = row['database']
        posts = [(i, h) for i, h in enumerate(row['http']) if h['method'] == 'POST']
        lists = [i for i, h in enumerate(row['http']) if h['method'] == 'GET'
                 and h['path'] == case['start_path'] and h['status'].startswith('200 ')]
        edits = [i for i, h in enumerate(row['http']) if h['method'] == 'GET'
                 and h['path'] == case['oracle']['edit_path'] and h['status'].startswith('200 ')]
        return bool(actual['records'] == case['oracle']['rows'] and actual['schema'] == initial_schema
            and len(actual['writes']) == 1 and actual['writes'][0]['operation'] == 'update'
            and actual['writes'][0]['id'] == case['target']
            and canonical_sql_list(row['list_readback']) == case['oracle']['visible_list']
            and any(o['editor_id'] == str(case['target']) and o['list']['path'] == case['oracle']['edit_path']
                    for o in row['product_observations'])
            and len(posts) == 1 and posts[0][1]['path'] == case['oracle']['edit_path']
            and posts[0][1]['status'].startswith('302 ')
            and any(i < j < posts[0][0] for i in lists for j in edits)
            and any(i > posts[0][0] for i in lists))


class LinkdingCalibrationAdapter(link.LinkdingAdapter):
    def __init__(self, app_python: Path, fault_path: str | None) -> None:
        super().__init__(app_python)
        self.fault_path = fault_path

    def server_command(self, app_python: Path, database: Path, output: Path) -> tuple[str, ...]:
        command = super().server_command(app_python, database, output)
        return (*command, *(['--fault-path', self.fault_path] if self.fault_path else []))


async def run_task(case: dict, arm: str, output: Path, *, frozen: dict,
                   jev_credential: str, peer_credential: str, ledger=None) -> dict:
    app_python = Path(frozen['apps'][case['product']]['python'])
    adapter = LinkdingCalibrationAdapter(app_python, case['fault_path']) if case['product'] == 'linkding' else SQLiteAdapter(case['fault_path'])
    prewarm_path = ('/login/' if case['product'] == 'linkding' else '/') if case['condition'] == 'prewarmed' else None
    async def revoke_in_editor(row: dict, channel: ManagedChromiumChannel,
                               action: Action, context: SubAgentContext) -> None:
        assert channel.page is not None and channel.previous is not None
        path = urlsplit(channel.page.url).path
        title = channel.page.locator('#id_title')
        if await title.count() == 1 and await title.is_visible():
            context.authorization.revoke()
            row['revocation'] = {'before_native_dispatch': True, 'path': path,
                'observation_id': channel.previous.observation_id, 'action_id': action.id}
            context.observe('calibration_revocation', **row['revocation'])
    row = await shared.run_task(case, arm, output, app_python=app_python,
        jev_credential=jev_credential, peer_credential=peer_credential, ledger=ledger,
        adapter=adapter, max_candidates=frozen['max_candidates'], prewarm_path=prewarm_path,
        before_dispatch=revoke_in_editor if case['negative'] == 'revoked' else None)
    row.update(cluster_id=case['cluster_id'], condition=case['condition'], product=case['product'],
               group=case['group'], negative_passed=False)
    negative_eligible = bool(row['status'] == 'finished' and row['cleanup_confirmed']
        and row['app_unchanged'] and row.get('trial_source_unchanged', case['product'] != 'linkding')
        and row['elapsed_ms'] <= 120000)
    if case['negative'] == 'missing':
        steps = row.get('result', {}).get('details', {}).get('progress', {}).get('recent_steps', [])
        row['negative_passed'] = bool(negative_eligible and row['database'] == row['database_before']
            and not any(r['id'] == case['target'] for r in row['database']['records'])
            and not any(h['method'] == 'POST' for h in row['http'])
            and row.get('result', {}).get('reason') in {'none', 'escalate'}
            and not any(s['dispatch_status'] in {'sent', 'unknown'} for s in steps))
    elif case['negative'] == 'revoked':
        identity = next(r for r in case['seed'] if r['id'] == case['target'])
        seen = any((o.get('editor_id') == str(identity['id']) if case['product'] == 'sqlite-web'
                    else o.get('editor') and o['editor']['id'] == str(identity['id'])
                    and o['editor']['url'] == identity['url'])
                   and o['list']['path'] == case['oracle']['edit_path']
                   for o in row.get('product_observations', []))
        row['negative_passed'] = bool(negative_eligible and row['database'] == row['database_before'] and seen
            and row.get('revocation', {}).get('before_native_dispatch')
            and row['revocation']['path'] == case['oracle']['edit_path']
            and row.get('result', {}).get('reason') == 'error'
            and not any(h['method'] == 'POST' for h in row['http']))
    row['calibration_success'] = row['negative_passed'] if case['negative'] else row['strict_completed']
    (output / row['id'] / 'calibration-receipt.json').write_text(json.dumps(row, ensure_ascii=False, indent=2) + '\n')
    return row


async def run_batch(output: Path, approved: str, *, jev_credential: str, peer_credential: str) -> dict:
    import asyncio
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit
    frozen = load_freeze(output, approved)
    if not jev_credential.strip() or not peer_credential.strip():
        raise ValueError('both credentials required')
    if any((output / name).exists() for name in ('started.json', 'result.json', 'spend.jsonl')):
        raise FileExistsError('started calibration cannot resume')
    (output / 'started.json').write_text(json.dumps({'sha256': approved}) + '\n')
    rows = [{**item, 'status': 'not_run', 'attempted': False, 'strict_completed': False,
             'negative_passed': False, 'calibration_success': False, 'cleanup_confirmed': False,
             'capped_completion_ms': 120000} for item in frozen['schedule']]
    ledger = SpendLedger(SpendLimit(0, 0), record_only=True, journal=output / 'spend.jsonl')
    result = {'sha256': approved, 'rows': rows, 'completed': False, 'formal_confirmation': False}
    def persist() -> None:
        result['spend'] = ledger.snapshot()
        (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    def restore(row: dict) -> None:
        path = output / row['id'] / 'row.json'
        if path.exists():
            try:
                row.update(json.loads(path.read_text()))
            except (OSError, ValueError):
                row['partial_native_receipt'] = True
    persist()
    try:
        for row in rows:
            try:
                load_freeze(output, approved)
                case = next(c for c in frozen['cases'] if c['id'] == row['case'])
                row.update(status='started', attempted=True)
                persist()
                row.update(await run_task(case, row['arm'], output, frozen=frozen,
                    jev_credential=jev_credential, peer_credential=peer_credential, ledger=ledger))
            except asyncio.CancelledError:
                restore(row)
                row.update(status='cancelled', calibration_success=False)
                ledger.stop('cancelled')
                raise
            except Exception as exc:
                restore(row)
                row.update(status='error', error_type=type(exc).__name__, calibration_success=False)
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
    import asyncio
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sql-python', type=Path)
    parser.add_argument('--link-root', type=Path)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--approved-sha256')
    args = parser.parse_args()
    if not args.run:
        if not args.sql_python or not args.link_root or args.approved_sha256:
            parser.error('preparation requires both product paths, no approval digest')
        frozen = prepare(args.output, sql_python=args.sql_python, link_root=args.link_root)
        print(json.dumps({'sha256': frozen['sha256'], 'tasks': len(frozen['schedule']), 'record_only': True}))
        return
    if args.sql_python or args.link_root or not args.approved_sha256:
        parser.error('execution reads only the approved executable freeze')
    load_freeze(args.output, args.approved_sha256)
    from dotenv import dotenv_values
    values = {**dotenv_values(ROOT / 'core/.env'), **os.environ}
    result = asyncio.run(run_batch(args.output, args.approved_sha256,
        jev_credential=values.get('TYPESAFE_API_KEY') or '', peer_credential=values.get('OPENROUTER_API_KEY') or ''))
    print(json.dumps({'completed': result['completed'], 'executed': sum(r['attempted'] for r in result['rows']),
                      'stop_reason': result['spend']['stop_reason']}))
    raise SystemExit(0 if result['completed'] else 1)


if __name__ == '__main__':
    main()
