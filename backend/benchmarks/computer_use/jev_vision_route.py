"""Frozen V/JT routing on owned synthetic web tasks; real host and Chromium."""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import time
from dataclasses import replace
from importlib.metadata import version

from tank_backend.agents.task_runtime import ExecutionRecord
from tank_backend.benchmarks.spend_ledger import SpendLedger
from tank_backend.llm.model_data import ModelRequest
from pathlib import Path

from agent_computer_use import action_builder, agent, contracts, controller, jev, model_view, visual_selector
from agent_computer_use.channels import dom
from benchmarks.computer_use import jev_box_crop
from benchmarks.computer_use.jev_image_dev import digest

ROOT = Path(__file__).resolve().parents[2]
PEER = dict(jev_box_crop.PEER)
JEV = dict(jev_box_crop.JEV)


def cases(*, followup: bool = False) -> list[dict]:
    result = []
    matrix = [('positive', 'form'), ('positive', 'grid'), ('positive', 'drawer'),
              ('absent', 'grid'), ('stale', 'form'), ('no_effect', 'form')]
    if followup:
        matrix += [('fallback', 'grid'), ('fallback', 'drawer'), ('fallback_absent', 'grid')]
    for scenario, layout in matrix:
        for order in range(2):
            key = f'{layout}-{scenario}-{order}'
            red = 'b' if order == 0 else 'a'
            slots = ['a', 'b']
            fields = ['work', 'archive'] if order == 0 else ['archive', 'work']
            form = '<form id="editor" aria-label="Asset editor" onsubmit="save(event)">' + ''.join(
                f'<label>{name.title()} title<input name="{name}" value="Draft" '
                f'oninput="trail.push(\'fill:{name}:\'+this.value)"></label>' for name in fields)
            form += '<button type="submit" data-kind="save">Save work</button><button type="submit" data-kind="preview">Preview</button></form>'
            grid = '<section id="markers" role="region" aria-label="Marker palette"><p>Choose the red marker</p><div class="tiles">'
            for slot in slots:
                color = '#d7191c' if slot == red and scenario not in {'absent', 'fallback_absent'} else '#2455d6'
                destination = 'entry' if layout == 'drawer' else 'picked'
                label = 'Option ' + slot.upper() if scenario.startswith('fallback') else 'button'
                grid += (f'<button class="tile" aria-label="{label}" aria-controls="{destination}" '
                         f'style="background:{color}" onclick="pick(\'{slot}\')"></button>')
            grid += '</div></section>'
            if layout == 'form':
                body = form
                intent = 'Set Work title to Launch and save work. Leave Archive title as Draft. Do not preview.'
            elif layout == 'grid':
                body = grid + '<section id="picked" role="region" aria-label="Selection" hidden>Selection recorded</section>'
                intent = 'Choose the red marker. If no red marker exists, stop without clicking any marker.'
            else:
                body = ('<section id="start" role="region" aria-label="Workspace"><button aria-controls="palette" onclick="begin()">Begin setup</button>'
                        '<button aria-controls="help" onclick="trail.push(\'help\');help.hidden=false">Help</button></section>'
                        '<section id="help" role="region" aria-label="Help" hidden>Help only</section>'
                        '<section id="palette" role="region" aria-label="Color step" hidden>' + grid + '</section>'
                        '<section id="entry" role="region" aria-label="Name step" hidden>' + form + '</section>')
                intent = 'Begin setup, choose the red marker, set Work title to Launch and save work. Leave Archive title as Draft. Do not open Help or preview.'
            script = """<script>
            window.trail=[];window.selected=null;
            function begin(){trail.push('begin');start.hidden=true;palette.hidden=false;}
            function pick(slot){trail.push('pick:'+slot);window.selected=slot;
                if(document.getElementById('entry')){palette.hidden=true;entry.hidden=false;}
                else{picked.hidden=false;document.querySelector('[aria-label=Result]').textContent='selected:'+colors[slot];}}
            function save(e){e.preventDefault();const kind=e.submitter.dataset.kind;trail.push(kind);
                if(kind==='preview')return;
                const work=editor.elements.work.value,archive=editor.elements.archive.value;
                if(!NO_EFFECT)document.querySelector('[aria-label=Result]').textContent=
                    work==='Launch'&&archive==='Draft'&&(!IS_DRAWER||colors[selected]==='red')?'saved:Launch':'wrong';}
            </script>""".replace('NO_EFFECT', json.dumps(scenario == 'no_effect')).replace('IS_DRAWER', json.dumps(layout == 'drawer'))
            colors = {s: 'red' if s == red and scenario not in {'absent', 'fallback_absent'} else 'blue' for s in slots}
            script = '<script>const colors=' + json.dumps(colors) + ';</script>' + script
            html = ('<!doctype html><meta charset="utf-8"><style>body{font:20px system-ui;margin:48px;background:#fafafa;color:#171717}label{display:block;margin:24px}input{font:inherit;margin-left:24px}button{font:inherit;padding:12px;margin:16px}.tiles{display:grid;grid-template-columns:180px 180px;gap:90px}.tile{width:140px;height:110px} [hidden]{display:none!important}</style>'
                    + body + '<output aria-label="Result">idle</output>' + script)
            goal = {'schema_version': 2, 'goal_id': 'goal-' + hashlib.sha256(key.encode()).hexdigest()[:16], 'scope': 'route-pilot', 'authorization_ref': 'current_task',
                    'intent': intent, 'objective': intent, 'constraints': ['Do not guess missing colors or change unrelated fields.'],
                    'allowed_operations': ['click', 'fill'], 'inputs': [],
                    'completion': [{'key': 'status:Result', 'value': 'selected:red' if layout == 'grid' else 'saved:Launch'}]}
            if layout != 'grid':
                goal['inputs'] = [{'key': 'work_title', 'purpose': 'Work title only', 'value': 'Launch',
                                   'field_label': 'Work title' if layout == 'drawer' else None}]
            expected = (['pick:' + red] if layout == 'grid' else
                        (['begin', 'pick:' + red] if layout == 'drawer' else []) + ['fill:work:Launch', 'save'])
            contracts.GoalContract.from_input(goal)
            result.append({'id': key, 'layout': layout, 'scenario': scenario, 'order': order,
                           'html': html, 'goal': goal, 'oracle': {'events': expected, 'red': red}})
    return result


def sources() -> dict[str, str]:
    modules = (action_builder, agent, contracts, controller, jev, model_view, visual_selector, dom)
    return {**jev_box_crop.sources(), **{str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [Path(__file__), *(Path(inspect.getfile(m)) for m in modules)]}}


def freeze_inputs(*, followup: bool = False) -> dict:
    items = cases(followup=followup)
    schedule = [{'id': c['id'] + '-' + arm, 'case': c['id'], 'arm': arm}
                for n, c in enumerate(items) for arm in (('v', 'jt') if n % 2 == 0 else ('jt', 'v'))]
    f = {'revision': 'vision-route-2' if followup else 'vision-route-1', 'followup': followup, 'cases': items, 'schedule': schedule, 'source_sha256': sources(),
         'versions': {n: version(n) for n in ('playwright', 'openai', 'typesafe-sdk', 'pillow')},
         'models': {'jev': JEV, 'peer': PEER}, 'record_only': True, 'seconds_per_task': 120,
         'max_actions': 6, 'max_observations': 24, 'retries': 0,
         'scope': 'owned synthetic Chromium pages only; peer receives synthetic PNG+text; Jev receives text',
         'price_nano_usd': {'jev': [42, 0], 'peer': [825, 4125]},
         'price_evidence': 'Jev historical frozen rate; peer OpenRouter catalog in Box comparison 2026-10-19; estimates only'}
    if followup:
        f['fallback_evidence'] = 'JT palette text control then visual_fallback with same binding and no palette guess; goal_completed preserves physical goal/path; new JT strict_completed and negative_passed additionally require this evidence'
    f['sha256'] = digest(f)
    return f


def prepare(output: Path, *, followup: bool = False) -> dict:
    f = freeze_inputs(followup=followup)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'freeze.json').write_text(json.dumps(f, ensure_ascii=False, indent=2) + '\n')
    return f


def load_freeze(output: Path, approved: str) -> dict:
    stored = json.loads((output / 'freeze.json').read_text())
    f = freeze_inputs(followup=stored.get('followup', False))
    if f['sha256'] != approved or stored != f:
        raise ValueError('route pilot freeze changed')
    return f


class VisionBaseline(visual_selector.VisualSelector):
    """Only the benchmark policy differs; same rule builder, model, actions and checks."""
    async def choose(self, goal: contracts.GoalContract, snapshot: contracts.Snapshot,
                     actions: contracts.ActionSet, context) -> contracts.DecisionResult:
        return await super().choose(goal, snapshot, replace(actions, reason='visual_required'), context)


def palette_evidence(journal: list[dict], events: list[dict]) -> dict:
    """Post-run evidence only; never changes a model reply or routing decision."""
    responses = {r['call_id']: r['response'] for r in journal if 'response' in r}
    response_order = {r['call_id']: i for i, r in enumerate(journal) if 'response' in r}
    purposes = {e['call_id']: e['purpose'] for e in events
                if e['kind'] == 'model_call' and e.get('phase') == 'finished'}
    controls, proofs, guesses, image_calls = {}, [], [], []
    for index, record in enumerate(journal):
        if 'request' not in record:
            continue
        request = record['request']
        peer = 'messages' in request
        packet = json.loads(request['messages'][1]['content'][0]['text']) if peer else request
        offered = {k: v for k, v in packet['questions']['next_action']['criteria'].items() if isinstance(v, dict)}
        if {v['label'] for v in offered.values()} != {'Option A', 'Option B'}:
            continue
        binding = packet['state']['binding']
        key = json.dumps(binding, sort_keys=True)
        call_id = record['call_id']
        if peer:
            image_calls.append(call_id)
            if (key in controls and response_order[controls[key]] < index
                    and purposes.get(call_id) == 'computer_use.visual_fallback'):
                proofs.append({'text_call_id': controls[key], 'visual_call_id': call_id, 'binding': binding})
        else:
            choice = responses.get(call_id, {}).get('choice')
            if choice in offered:
                guesses.append(call_id)
            elif choice in ('none', 'ambiguous', 'need_more_context', 'escalate'):
                controls[key] = call_id
    return {'fallback_verified': bool(proofs) and not guesses, 'fallback_proofs': proofs,
            'palette_guesses': guesses, 'palette_image_calls': image_calls}


async def run_task(case: dict, arm: str, output: Path, *, jev_credential: str,
                   peer_credential: str, ledger: SpendLedger | None = None) -> dict:
    import base64
    from dataclasses import asdict
    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext, SubAgentRequest
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.model_data import ModelDataScope
    from tank_backend.llm.profile import LLMProfile

    if arm not in ('v', 'jt') or not jev_credential.strip() or not peer_credential.strip():
        raise ValueError('both model credentials and a declared arm required')
    row_id = case['id'] + '-' + arm
    task_id = 'route-' + hashlib.sha256(row_id.encode()).hexdigest()[:16]
    path = output / row_id
    path.mkdir(exist_ok=False)
    started = time.monotonic()
    own_ledger = ledger is None
    if ledger is None:
        ledger = SpendLedger(SpendLimit(0, 0), record_only=True, journal=path / 'spend.jsonl')
    ledger.start_trial(row_id, SpendLimit(0, 0))
    row = {'id': row_id, 'task_id': task_id, 'case': case['id'], 'arm': arm, 'layout': case['layout'],
           'scenario': case['scenario'], 'status': 'started', 'cleanup_confirmed': False,
           'strict_completed': False, 'negative_passed': False, 'events': [], 'calls': [],
           'visual_captures': 0, 'rules_actions': 0, 'page_state': {}, 'mutation_applied': False}
    events, calls = row['events'], row['calls']
    channel = None
    ctx = None
    server = None

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 5)
            data = case['html'].encode()
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n'
                         + f'Content-Length: {len(data)}\r\nConnection: close\r\n\r\n'.encode() + data)
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    class Observer:
        def on_event(self, kind: str, metadata: dict) -> None:
            events.append({'kind': kind, **metadata})

    class Capture:
        async def request(self, call_id: str, request: ModelRequest) -> None:
            item = {'call_id': call_id, 'request': request.parameters, 'images': []}
            for message in request.parameters.get('messages', []):
                if isinstance(message['content'], list):
                    for part in message['content']:
                        if part['type'] == 'image_url':
                            png = base64.b64decode(part['image_url']['url'].split(',', 1)[1])
                            name = f'{call_id}.png'
                            (path / name).write_bytes(png)
                            item['images'].append({'path': name, 'sha256': hashlib.sha256(png).hexdigest()})
            calls.append(item)
            with (path / 'calls.jsonl').open('a') as journal:
                journal.write(json.dumps(item, ensure_ascii=False) + '\n')

        async def response(self, call_id: str, response: dict) -> None:
            with (path / 'calls.jsonl').open('a') as journal:
                journal.write(json.dumps({'call_id': call_id, 'response': response}, ensure_ascii=False) + '\n')
            if case['scenario'] == 'stale' and not row['mutation_applied']:
                assert channel is not None and channel.page is not None
                await channel.page.locator('input,button').evaluate_all(
                    'nodes => nodes.forEach(node => node.replaceWith(node.cloneNode(true)))')
                row['mutation_applied'] = True

    async def audit(record: ExecutionRecord) -> None:
        with (path / 'audit.jsonl').open('a') as journal:
            journal.write(json.dumps(asdict(record)) + '\n')

    try:
        server = await asyncio.start_server(serve, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]
        channel = dom.ManagedChromiumChannel(dom.BrowserConfig(scope=case['goal']['scope'], url=f'http://127.0.0.1:{port}/'))
        selector = VisionBaseline(channel) if arm == 'v' else visual_selector.VisualSelector(channel)
        host = controller.ComputerUseController(channel, channel, selector=selector)
        ctx = SubAgentContext(SubAgentAuthorization(frozenset({'desktop', 'network'})), SubAgentBudget(),
            asyncio.Event(), deadline=started + 120, max_actions=6, max_observations=24,
            model_data_scope=ModelDataScope(frozenset({'text', 'image'}), 32 * 1024 * 1024),
            observer=Observer(), audit=audit, model_capture=Capture(), model_policy=BenchmarkModelPolicy(ledger, ()))
        ctx.runtime.configure_decision_model(task_id, DecisionModelProfile(
            JEV['url'], JEV['model'], 'TYPESAFE_API_KEY'), credential=jev_credential)
        ctx.runtime.configure_visual_model(task_id, LLMProfile('route-peer', peer_credential, PEER['model'],
            PEER['url'], temperature=0, max_tokens=PEER['max_tokens']))
        result = await host.run(SubAgentRequest(case['goal']['intent'], '', task_id, case['goal']), ctx)
        row['result'] = result.to_output().metadata['task_result']
        row['status'] = 'finished'
        assert channel.page is not None
        row['page_state'] = await channel.page.evaluate("""() => ({trail:window.trail,
            result:document.querySelector('[aria-label=Result]').textContent,
            fields:Object.fromEntries([...document.querySelectorAll('input')].map(n=>[n.name,n.value]))})""")
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
                await close()
            except BaseException as exc:
                errors.append(type(exc).__name__)
                if not isinstance(exc, Exception):
                    raise
        if server is not None:
            server.close()
            await server.wait_closed()
        row['cleanup_confirmed'] = not errors and (channel is None or channel.closed and
            (channel.browser is None or not channel.browser.is_connected()))
        row['cleanup_errors'] = errors
        if 'result' in row:
            row['result']['cleanup'] = 'confirmed' if row['cleanup_confirmed'] else 'unknown'
        if not row['cleanup_confirmed']:
            ledger.stop('cleanup_failed')
        row['usage'] = ctx.budget.snapshot() if ctx is not None else {}
        row['visual_captures'] = sum(e['kind'] == 'task_execution' and e.get('operation') == 'computer_use.capture' and e.get('phase') == 'finished' for e in events)
        row['rules_actions'] = sum(e['kind'] == 'computer_use_dispatch' and e.get('selected_by') == 'rules' for e in events)
        row['elapsed_ms'] = (time.monotonic() - started) * 1000
        state, task_result = row['page_state'], row.get('result', {})
        trail = state.get('trail', [])
        clean = row['cleanup_confirmed'] and not errors
        row['strict_completed'] = bool(clean and row['elapsed_ms'] <= 120000 and case['scenario'] in {'positive', 'fallback'} and task_result.get('status') == 'completed'
            and trail == case['oracle']['events'] and state.get('result') == case['goal']['completion'][0]['value'])
        row['goal_completed'] = row['strict_completed']
        journal_path = path / 'calls.jsonl'
        journal = [json.loads(line) for line in journal_path.read_text().splitlines()] if journal_path.exists() else []
        row.update(palette_evidence(journal, events))
        route_valid = arm != 'jt' or not case['scenario'].startswith('fallback') or row['fallback_verified']
        row['strict_completed'] = row['goal_completed'] and route_valid
        if case['scenario'] in {'absent', 'fallback_absent'}:
            row['negative_passed'] = bool(clean and not trail and task_result.get('reason') in ('none', 'no_progress'))
        elif case['scenario'] == 'stale':
            row['negative_passed'] = bool(clean and row['mutation_applied'] and not trail and task_result.get('reason') == 'stale_reference')
        elif case['scenario'] == 'no_effect':
            row['negative_passed'] = bool(clean and trail == case['oracle']['events'] and task_result.get('reason') == 'effect_unknown'
                and task_result.get('details', {}).get('pending_effect') and state.get('result') == 'idle')
        row['exit_correct'] = row['negative_passed']
        row['negative_passed'] = row['exit_correct'] and route_valid
        row['capped_completion_ms'] = (row['elapsed_ms'] if row['strict_completed'] else 120000) if case['scenario'] in {'positive', 'fallback'} else None
        ledger.finish_trial()
        if own_ledger:
            ledger.close()
        (path / 'row.json').write_text(json.dumps(row, ensure_ascii=False, indent=2) + '\n')
    return row


async def run_batch(output: Path, approved: str, *, jev_credential: str, peer_credential: str) -> dict:
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit
    frozen = load_freeze(output, approved)
    if not jev_credential.strip() or not peer_credential.strip():
        raise ValueError('both credentials required')
    if any((output / n).exists() for n in ('started.json', 'result.json', 'spend.jsonl')):
        raise FileExistsError('started batch cannot resume')
    (output / 'started.json').write_text(json.dumps({'sha256': approved}) + '\n')
    rows = [{**item, 'status': 'not_run', 'scenario': next(c['scenario'] for c in frozen['cases'] if c['id'] == item['case']),
             'strict_completed': False, 'negative_passed': False, 'cleanup_confirmed': False}
            for item in frozen['schedule']]
    result = {'sha256': approved, 'rows': rows, 'completed': False}
    ledger = SpendLedger(SpendLimit(0, 0), record_only=True, journal=output / 'spend.jsonl')

    def persist() -> None:
        result['spend'] = ledger.snapshot()
        (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')

    persist()
    try:
        for row in rows:
            load_freeze(output, approved)
            case = next(c for c in frozen['cases'] if c['id'] == row['case'])
            try:
                row.update(await run_task(case, row['arm'], output, jev_credential=jev_credential,
                                          peer_credential=peer_credential, ledger=ledger))
            except asyncio.CancelledError:
                saved = output / row['id'] / 'row.json'
                if saved.exists():
                    row.update(json.loads(saved.read_text()))
                else:
                    row['status'] = 'cancelled'
                ledger.stop('cancelled')
                raise
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
    from dotenv import dotenv_values
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--followup', action='store_true', help='prepare the 36-task semantic-gap extension')
    parser.add_argument('--approved-sha256')
    args = parser.parse_args()
    if not args.run:
        if args.approved_sha256:
            parser.error('preparation has no approval digest')
        f = prepare(args.output, followup=args.followup)
        print(json.dumps({'sha256': f['sha256'], 'tasks': len(f['schedule']), 'record_only': True}))
        return
    if not args.approved_sha256 or args.followup:
        parser.error('execution uses the frozen digest only')
    values = {**dotenv_values(ROOT / 'core/.env'), **os.environ}
    result = asyncio.run(run_batch(args.output, args.approved_sha256,
        jev_credential=values.get('TYPESAFE_API_KEY') or '', peer_credential=values.get('OPENROUTER_API_KEY') or ''))
    print(json.dumps({'completed': result['completed'], 'stop_reason': result['spend']['stop_reason']}))
    raise SystemExit(0 if result['completed'] else 1)


if __name__ == '__main__':
    main()
