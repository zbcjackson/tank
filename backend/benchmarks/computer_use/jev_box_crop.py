"""Read-only frozen Box representation comparison; no desktop executor."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import math
import time
from dataclasses import asdict
from pathlib import Path

from PIL import Image, ImageDraw

from agent_computer_use.jev_image import normalize_frame
from agent_computer_use.visual_selector import VisualFrame
from benchmarks.computer_use import jev_image_eval as evaluation
from benchmarks.computer_use.jev_image_dev import digest
from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext, SubAgentStopped
from tank_backend.agents.task_runtime import ExecutionRecord
from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, SpendLimitExceeded
from tank_backend.llm.decision_image import box_questions, image_request
from tank_backend.llm.decision_profile import DecisionModelProfile
from tank_backend.llm.model_call import model_purpose
from tank_backend.llm.model_data import ModelDataScope, ModelImageAsset, ModelRequest
from tank_backend.llm.profile import LLMProfile
from tank_backend.tools.computer_observation import Observation

ROOT = Path(__file__).resolve().parents[2]
PEER = {"model": "google/gemini-3.8-flash", "url": "https://openrouter.ai/api/v1", "max_tokens": 4096}
JEV = {"model": "jev-1.14.0", "url": evaluation.JEV["url"]}
INSTRUCTION = "Read-only localization in the attached image. Do not infer locations from identifiers."


def make_view(png: bytes, roi: tuple[int, int, int, int]) -> tuple[bytes, dict]:
    with Image.open(io.BytesIO(png)) as image:
        left, top, right, bottom = roi
        if not 0 <= left < right <= image.width or not 0 <= top < bottom <= image.height:
            raise ValueError("crop outside source")
        stream = io.BytesIO()
        image.crop(roi).save(stream, "PNG")
    frame, cropped = Observation.capture(stream.getvalue(), session_id="offline-box", display_id=1)
    prepared = normalize_frame(VisualFrame("offline-box", frame, cropped, ()))
    return prepared.asset.data, {"roi": list(roi), "size": list(prepared.size), "content": list(prepared.content)}


def score(label: dict, view: dict, answer: dict) -> dict:
    rectangles = label["rectangles"]
    expected = "none" if not rectangles else "one" if len(rectangles) == 1 else "several"
    count = answer["cardinality"]
    result: dict[str, object] = {"cardinality_correct": count == expected, "geometry_valid": True,
              "center_hit": False, "whole_hit": False, "correct": count == expected and expected != "one",
              "screen_point": None, "offset": None, "iou": None}
    if count != "one":
        return result
    box = answer["box"]
    width, height = view["size"]
    left, top, right, bottom = view["content"]
    if (not isinstance(box, (list, tuple)) or len(box) != 4
            or any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in box)
            or not left <= box[0] * width < box[2] * width <= right
            or not top <= box[1] * height < box[3] * height <= bottom):
        result["geometry_valid"] = False
        return result
    rx0, ry0, rx1, ry1 = view["roi"]
    base = [rx0 + (box[0] * width - left) * (rx1 - rx0) / (right - left),
            ry0 + (box[1] * height - top) * (ry1 - ry0) / (bottom - top),
            rx0 + (box[2] * width - left) * (rx1 - rx0) / (right - left),
            ry0 + (box[3] * height - top) * (ry1 - ry0) / (bottom - top)]
    bw, bh = label["base_size"]
    x0, y0, x1, y1 = label["crop"]
    ox, oy = label["origin"]
    screen = [x0 + base[0] * (x1 - x0) / bw + ox, y0 + base[1] * (y1 - y0) / bh + oy,
              x0 + base[2] * (x1 - x0) / bw + ox, y0 + base[3] * (y1 - y0) / bh + oy]
    point = [min(x1 - 1 + ox, math.floor((screen[0] + screen[2]) / 2 + .5)),
             min(y1 - 1 + oy, math.floor((screen[1] + screen[3]) / 2 + .5))]
    result["screen_point"] = point
    if expected == "one":
        x, y, w, h = rectangles[0]
        inset = min(w, h) * .1
        hit = x + inset <= point[0] <= x + w - inset and y + inset <= point[1] <= y + h - inset
        result.update(center_hit=hit, correct=hit, whole_hit=x <= point[0] < x + w and y <= point[1] < y + h,
                      offset=[point[0] - x - w / 2, point[1] - y - h / 2])
        intersection = max(0, min(x + w, screen[2]) - max(x, screen[0])) * max(0, min(y + h, screen[3]) - max(y, screen[1]))
        union = w * h + (screen[2] - screen[0]) * (screen[3] - screen[1]) - intersection
        result["iou"] = intersection / union
    return result


def sources() -> dict:
    import inspect
    return {**evaluation.sources(), **{str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (Path(__file__), ROOT / 'uv.lock', Path(inspect.getfile(normalize_frame)), Path(inspect.getfile(Observation)))}}


def versions() -> dict:
    from importlib.metadata import version
    return {name: version(name) for name in ('pillow', 'openai', 'typesafe-sdk')}


def asset(png: bytes) -> ModelImageAsset:
    return ModelImageAsset('tank-image-' + hashlib.sha256(png).hexdigest()[:32], 'asset-0', 'image/png', png)


def packet(case: dict, view: dict, png: bytes, model: str) -> dict:
    stage = {'instruction': INSTRUCTION, 'target': case['target'], 'snapshot': {
        'case_id': case['id'], 'size': view['size'], 'content': view['content']}}
    if model == 'peer':
        return {'model': PEER['model'], 'messages': evaluation.qwen_messages(stage, png),
                'max_tokens': PEER['max_tokens'], 'temperature': 0, 'stream': False,
                'response_format': {'type': 'json_object'}}
    profile = DecisionModelProfile(JEV['url'], JEV['model'], 'TYPESAFE_API_KEY', images=True)
    return image_request(profile, {'task': INSTRUCTION, 'snapshot': stage['snapshot']},
                         asset(png), box_questions(case['target'])).parameters


def prepare(output: Path, *, textedit: Path, calculator: Path, catalog: Path) -> dict:
    catalog_data = json.loads(catalog.read_text())
    peer = next(m for m in catalog_data['data'] if m['id'] == PEER['model'])
    if ('image' not in peer['architecture']['input_modalities']
            or 'response_format' not in peer['supported_parameters']):
        raise ValueError('peer catalog lacks image/JSON support')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'images').mkdir()
    public = {'cases': [], 'views': {}}
    labels, provenance = {}, []

    def add_source(source_id: str, png: bytes, crop: list, origin: list,
                   targets: list, roi: tuple, phase: str, layout: str) -> None:
        with Image.open(io.BytesIO(png)) as im:
            size = im.size
        (output / 'images' / (source_id + '-base.png')).write_bytes(png)
        views = {}
        for name, region in [('full', (0, 0, *size))] + ([('region', roi)] if phase == 'main' else []):
            prepared, metadata = make_view(png, region)
            path = 'images/' + source_id + '-' + name + '.png'
            (output / path).write_bytes(prepared)
            views[name] = {**metadata, 'path': path}
        public['views'][source_id] = views
        for target_id, description, rectangles in targets:
            for x, y, w, h in rectangles:
                rect_left = (x - origin[0] - crop[0]) * size[0] / (crop[2] - crop[0])
                t = (y - origin[1] - crop[1]) * size[1] / (crop[3] - crop[1])
                rr = rect_left + w * size[0] / (crop[2] - crop[0])
                bb = t + h * size[1] / (crop[3] - crop[1])
                if not roi[0] <= rect_left < rr <= roi[2] or not roi[1] <= t < bb <= roi[3]:
                    raise ValueError('declared generic ROI removes a positive target')
            case_id = source_id + '-' + target_id
            public['cases'].append({'id': case_id, 'source': source_id, 'target': description,
                                    'phase': phase, 'layout': layout})
            labels[case_id] = {'rectangles': rectangles, 'base_size': list(size), 'crop': crop, 'origin': origin}

    for layout, root, ids in (
        ('textedit', textedit, ('scene-01-p0-image', 'scene-02-p1-image')),
        ('calculator', calculator, ('jev-image-multiply', 'jev-image-add')),
    ):
        records = [json.loads(line) for line in (root / 'calls.jsonl').read_text().splitlines()]
        for pos, source_case in enumerate(ids):
            q = next(r for r in records if r.get('trial', r.get('case_id')) == source_case
                     and 'request' in r and r['images'])
            state = q['request']['state']
            metadata = state['image_metadata']
            info = q['images'][0]
            png = (root / info['path']).read_bytes()
            with Image.open(io.BytesIO(png)) as im:
                w, h = im.size
            if (hashlib.sha256(png).hexdigest() != info['sha256'] or metadata['orientation'] != 1
                    or metadata['size'] != [w, h] or metadata['content'] != [0, 0, w, h]):
                raise ValueError('original request image is not the declared full upright frame')
            if layout == 'textedit':
                nodes = state['full_ax']['elements']
                def matches(names):
                    return [e['frame'] for e in nodes if e.get('description') in names]
                italic, font, multiple = matches({'italic'}), matches({'typeface'}), matches({'align left', 'align center', 'align right', 'fully justify'})
                targets = [('italic', 'the italic button in the formatting toolbar', italic),
                           ('typeface', 'the font-family selector showing Helvetica', font),
                           ('many', 'the alignment buttons in the formatting toolbar', multiple)]
                roi = (0, round(h * .03), w, round(h * .085))
            else:
                nodes = state['snapshot']['elements']
                def matches(names):
                    return [e['bounds'] for e in nodes if e.get('label') in names and e.get('bounds')]
                equal, clear, multiple = matches({'Equals'}), matches({'All Clear'}), matches(set('0123456789'))
                targets = [('equals', 'the Equals button', equal), ('clear', 'the AC (All Clear) button', clear),
                           ('many', 'the number digit buttons, 0 through 9', multiple)]
                roi = (0, round(h * .28), w, h)
            if [len(t[2]) for t in targets] != [1, 1, 4 if layout == 'textedit' else 10]:
                raise ValueError('independent AX target cardinality changed')
            targets.append(('absent', 'the Export CSV button in this window', []))
            frame = metadata['source']
            add_source(f'{layout}-{pos}', png, frame['crop'], frame['display_geometry'][1:3], targets, roi, 'main', layout)
            provenance.append({'source': f'{layout}-{pos}', 'original_root': str(root),
                'calls_sha256': hashlib.sha256((root / 'calls.jsonl').read_bytes()).hexdigest(), 'record': q})

    for i, kind in enumerate(('one', 'none', 'several')):
        image = Image.new('RGB', (800, 600), 'white')
        draw = ImageDraw.Draw(image)
        rectangles = [[540, 180, 140, 140]] if kind != 'none' else []
        if kind == 'several':
            rectangles.append([100, 180, 140, 140])
        for x, y, w, h in rectangles:
            draw.rectangle((x, y, x + w - 1, y + h - 1), fill='red')
        if kind == 'none':
            draw.rectangle((540, 180, 679, 319), fill='blue')
        stream = io.BytesIO()
        image.save(stream, 'PNG')
        add_source(f'control-{i}', stream.getvalue(), [0, 0, 800, 600], [0, 0],
                   [('target', 'the red square', rectangles)], (0, 0, 800, 600), 'control', 'synthetic')
    public['cases'].sort(key=lambda c: c['phase'] != 'control')
    schedule, previews = [], {}
    for number, case in enumerate(public['cases']):
        variants = [(view, model) for view in public['views'][case['source']] for model in ('jev', 'peer')]
        offset = number % len(variants)
        for view, model in variants[offset:] + variants[:offset]:
            trial = case['id'] + '-' + view + '-' + model
            schedule.append({'id': trial, 'case': case['id'], 'view': view, 'model': model, 'phase': case['phase']})
            v = public['views'][case['source']][view]
            previews[trial] = packet(case, v, (output / v['path']).read_bytes(), model)
    for name, data in [('public.json', public), ('private.json', labels), ('provenance.json', provenance),
                       ('catalog.json', catalog_data), ('previews.json', previews)]:
        (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    frozen = {'revision': 'box-crop-1', 'source_sha256': sources(), 'versions': versions(),
              'files': {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in output.rglob('*') if p.is_file()},
              'schedule': schedule, 'models': {'jev': JEV, 'peer': PEER}, 'record_only': True,
              'seconds_per_trial': 120, 'contract_gate': 'all six control scores correct before main',
              'scope': 'saved owned experiment windows; no desktop authorization or executor'}
    frozen['sha256'] = digest(frozen)
    (output / 'freeze.json').write_text(json.dumps(frozen, indent=2) + '\n')
    return frozen


def load_freeze(output: Path, approved: str) -> dict:
    f = json.loads((output / 'freeze.json').read_text())
    if (f['sha256'] != approved or digest({k: v for k, v in f.items() if k != 'sha256'}) != approved
            or f['source_sha256'] != sources() or f['versions'] != versions()
            or f['models'] != {'jev': JEV, 'peer': PEER}
            or any(hashlib.sha256((output / p).read_bytes()).hexdigest() != sha for p, sha in f['files'].items())):
        raise ValueError('Box crop freeze changed')
    return f


async def run_batch(output: Path, approved: str, *, jev_credential: str, peer_credential: str) -> dict:
    frozen = load_freeze(output, approved)
    if not jev_credential.strip() or not peer_credential.strip():
        raise ValueError('both credentials required')
    if any((output / name).exists() for name in ('started.json', 'result.json', 'calls.jsonl', 'spend.jsonl')):
        raise FileExistsError('started experiments cannot be resumed')
    public = json.loads((output / 'public.json').read_text())
    labels = json.loads((output / 'private.json').read_text())
    previews = json.loads((output / 'previews.json').read_text())
    cases = {c['id']: c for c in public['cases']}
    rows = [{**s, 'status': 'not_run', 'score': {}, 'cleanup_confirmed': False} for s in frozen['schedule']]
    report = {'sha256': approved, 'rows': rows, 'completed': False, 'desktop_operations': 0}
    (output / 'started.json').write_text(json.dumps({'sha256': approved, 'record_only': True}) + '\n')
    ledger = SpendLedger(SpendLimit(0, 0), record_only=True, journal=output / 'spend.jsonl')

    def persist():
        report['spend'] = ledger.snapshot()
        (output / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

    persist()
    try:
        with (output / 'calls.jsonl').open('x') as journal, (output / 'audit.jsonl').open('x') as audits:
            for row in rows:
                if row['phase'] == 'main' and any(not r['score'].get('correct') for r in rows if r['phase'] == 'control'):
                    ledger.stop('contract_gate')
                    break
                load_freeze(output, approved)
                case = cases[row['case']]
                view = public['views'][case['source']][row['view']]
                png = (output / view['path']).read_bytes()
                trial = row['id']

                class Policy(BenchmarkModelPolicy):
                    count = 0

                    def reserve(self, call_id: str, request: ModelRequest) -> None:
                        if self.count:
                            ledger.stop('duplicate_call')
                            raise SpendLimitExceeded('duplicate_call')
                        super().reserve(call_id, request)
                        self.count += 1

                class Capture:
                    async def request(self, call_id: str, request: ModelRequest) -> None:
                        if request.parameters != previews[trial] or tuple(a.data for a in request.images) != ((png,) if row['model'] == 'jev' else ()):
                            raise ValueError('request differs from frozen preview')
                        journal.write(json.dumps({'trial': trial, 'call_id': call_id, 'request': request.parameters,
                            'images': [{'sha256': hashlib.sha256(a.data).hexdigest(), 'part': a.part} for a in request.images],
                            'headers': dict(request.headers)}, ensure_ascii=False) + '\n')
                        journal.flush()

                    async def response(self, call_id: str, response: dict) -> None:
                        journal.write(json.dumps({'trial': trial, 'call_id': call_id, 'response': response}, ensure_ascii=False) + '\n')
                        journal.flush()

                async def audit(record: ExecutionRecord) -> None:
                    audits.write(json.dumps(asdict(record)) + '\n')
                    audits.flush()

                ledger.start_trial(trial, SpendLimit(0, 0))
                context = SubAgentContext(SubAgentAuthorization(frozenset({'network'})), SubAgentBudget(),
                    asyncio.Event(), deadline=time.monotonic() + frozen['seconds_per_trial'], max_actions=0, max_observations=0,
                    model_policy=Policy(ledger, ()), model_capture=Capture(), audit=audit,
                    model_data_scope=ModelDataScope(frozenset({'text', 'image'}), 32 * 1024 * 1024))
                started = time.monotonic()
                row['status'] = 'started'
                try:
                    context.runtime.bind(trial)
                    with model_purpose('benchmark.box_crop.' + row['model']):
                        if row['model'] == 'peer':
                            context.runtime.configure_visual_model(trial, LLMProfile('box-peer', peer_credential,
                                PEER['model'], PEER['url'], temperature=0, max_tokens=PEER['max_tokens']))
                            model = context.runtime.visual_model
                            assert model is not None
                            text = await model.complete_json(previews[trial]['messages'])
                            row['raw_text'] = text
                            try:
                                answer = evaluation.parse_location(text)
                            except ValueError:
                                raise SubAgentStopped('invalid_location') from None
                        else:
                            context.runtime.configure_decision_model(trial, DecisionModelProfile(
                                JEV['url'], JEV['model'], 'TYPESAFE_API_KEY', images=True), credential=jev_credential)
                            model = context.runtime.decision_model
                            assert model is not None
                            answer_raw = await model.locate_image(
                                state={k: v for k, v in previews[trial]['state'].items() if k != 'image'},
                                image=asset(png), target=case['target'])
                            answer = {**asdict(answer_raw), 'cardinality': answer_raw.cardinality.choice,
                                      'box': list(answer_raw.box)}
                    row.update(status='returned', answer=answer, score=score(labels[case['id']], view, answer))
                except asyncio.CancelledError:
                    row['status'] = 'cancelled'
                    ledger.stop('cancelled')
                    raise
                except SubAgentStopped as exc:
                    row.update(status='invalid' if exc.reason in {'invalid_location', 'invalid_decision'} else 'error', reason=exc.reason)
                    if row['status'] == 'error':
                        ledger.stop('operational_error')
                except Exception as exc:
                    row.update(status='error', error_type=type(exc).__name__)
                    ledger.stop('operational_error')
                finally:
                    try:
                        await context.runtime.aclose()
                        row['cleanup_confirmed'] = True
                    except BaseException as exc:
                        row['cleanup_error'] = type(exc).__name__
                        ledger.stop('cleanup_failed')
                        if not isinstance(exc, Exception):
                            raise
                    finally:
                        row.update(known_tokens=context.budget.total_tokens, elapsed_ms=(time.monotonic() - started) * 1000)
                        ledger.finish_trial()
                        persist()
                if ledger.snapshot()['stop_reason']:
                    break
            report['completed'] = ledger.snapshot()['stop_reason'] is None and all(r['status'] in {'returned', 'invalid'} and r['cleanup_confirmed'] for r in rows)
    finally:
        ledger.close()
        persist()
    return report


def main() -> None:
    import argparse
    import os
    from dotenv import dotenv_values
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--textedit', type=Path)
    parser.add_argument('--calculator', type=Path)
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--approved-sha256')
    args = parser.parse_args()
    if not args.run:
        if not all((args.textedit, args.calculator, args.catalog)) or args.approved_sha256:
            parser.error('preparation requires three source paths and no execution digest')
        frozen = prepare(args.output, textedit=args.textedit, calculator=args.calculator, catalog=args.catalog)
        print(json.dumps({'sha256': frozen['sha256'], 'planned': len(frozen['schedule'])}))
        return
    if not args.approved_sha256 or any((args.textedit, args.calculator, args.catalog)):
        parser.error('execution uses only the frozen directory and digest')
    values = {**dotenv_values(ROOT / 'core/.env'), **os.environ}
    result = asyncio.run(run_batch(args.output, args.approved_sha256,
        jev_credential=values.get('TYPESAFE_API_KEY') or '', peer_credential=values.get('OPENROUTER_API_KEY') or ''))
    print(json.dumps({'completed': result['completed'], 'spend': result['spend']['batch'], 'stop_reason': result['spend']['stop_reason']}))
    raise SystemExit(0 if result['completed'] else 1)


if __name__ == '__main__':
    main()
