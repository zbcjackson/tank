"""No-model, read-only caret diagnosis on owned Chromium fixture pages."""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import io
import json
import time
from pathlib import Path

from PIL import Image, ImageChops

from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel, _HIDE_CARET
from agent_computer_use.contracts import Action, Binding, snapshot_json
from benchmarks.computer_use import jev_vision_route
from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext

ROOT = Path(__file__).resolve().parents[2]
POLICIES = ('initial', 'hide', 'production')
DELAYS = (.05, .25, .55, .85, 1.1, 1.4, 1.7, 2.0)


def sources() -> dict[str, str]:
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), Path(inspect.getfile(ManagedChromiumChannel)),
                      Path(inspect.getfile(jev_vision_route)))}


async def run(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    frozen = {'source_sha256': sources(), 'policies': POLICIES, 'delays_seconds': DELAYS,
              'source_cases': ['form-positive-0', 'form-positive-1'],
              'setup': 'seed Work=Launch in HTML, focus and select its end before observation',
              'model_calls': 0, 'task_inputs': 0}
    (output / 'freeze.json').write_text(json.dumps(frozen, indent=2) + '\n')
    report = {'contexts': [], 'checks': [], 'model_calls': 0, 'task_inputs': 0}
    cases = {c['id']: c for c in jev_vision_route.cases()}
    for order in range(2):
        html = cases[f'form-positive-{order}']['html'].replace('name="work" value="Draft"', 'name="work" value="Launch"')
        for policy in POLICIES:
            if sources() != frozen['source_sha256']:
                raise ValueError('diagnostic source changed')
            name = f'order-{order}-{policy}'
            folder = output / name
            folder.mkdir()
            context_row = {'id': name, 'policy': policy, 'order': order, 'cleanup_confirmed': False}
            report['contexts'].append(context_row)
            events: list[dict] = []
            frames: list[dict] = []
            class Observer:
                def on_event(self, kind: str, metadata: dict) -> None:
                    if kind == 'computer_use_freshness':
                        events.append(dict(metadata))

            class Channel(ManagedChromiumChannel):
                async def visual_png(self) -> bytes:
                    assert self.page is not None
                    if policy == 'production':
                        png = await super().visual_png()
                    else:
                        if policy == 'hide':
                            await self.page.evaluate(_HIDE_CARET, self.namespace)
                        png = await self.page.screenshot(type='png', scale='css', caret='initial')
                    path = f'{len(frames):02}.png'
                    (folder / path).write_bytes(png)
                    frames.append({'path': path, 'sha256': hashlib.sha256(png).hexdigest()})
                    return png

            async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 5)
                    body = html.encode()
                    writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n'
                        + f'Content-Length: {len(body)}\r\nConnection: close\r\n\r\n'.encode() + body)
                    await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()

            server = None
            channel = None
            ctx = SubAgentContext(SubAgentAuthorization(frozenset({'desktop', 'network'})),
                SubAgentBudget(), asyncio.Event(), deadline=time.monotonic() + 30,
                observer=Observer(), max_actions=0, max_observations=0)
            ctx.runtime.bind(name)
            try:
                server = await asyncio.start_server(serve, '127.0.0.1', 0)
                port = server.sockets[0].getsockname()[1]
                channel = Channel(BrowserConfig(scope='diagnosis', url=f'http://127.0.0.1:{port}/'))
                await channel.start(ctx)
                assert channel.page is not None and channel.browser is not None
                context_row['browser_version'] = channel.browser.version
                await channel.page.locator('input[name=work]').focus()
                await channel.page.locator('input[name=work]').evaluate('e => e.setSelectionRange(e.value.length,e.value.length)')
                snapshot = await channel.observe('diagnosis', ctx)
                target = next(e for e in snapshot.elements if e.label == 'Save work')
                action = Action('save', target.ref, 'click', None)
                binding = Binding('diagnosis', 1, snapshot.observation_id, snapshot.scope, snapshot.generation, 'actions')
                original_view = channel.view
                captured = await channel.capture(snapshot, ctx)
                assert frames[-1]['sha256'] == captured.frame.image_sha256
                context_row.update(snapshot=snapshot_json(snapshot), initial_frame=frames[0])
                started = time.monotonic()
                for delay in DELAYS:
                    await asyncio.sleep(max(0, delay - (time.monotonic() - started)))
                    offset = len(events)
                    current = await channel.is_current(binding, action, ctx)
                    assert len(frames) == 2 + len([c for c in report['checks'] if c['context'] == name])
                    png = (folder / frames[-1]['path']).read_bytes()
                    with Image.open(io.BytesIO(captured.png)) as a, Image.open(io.BytesIO(png)) as b:
                        diff = ImageChops.difference(a.convert('RGB'), b.convert('RGB'))
                        bbox = diff.getbbox()
                        # Count pixels, preserving RGB grouping without deprecated getdata.
                        colors = diff.getcolors(diff.width * diff.height)
                        assert colors is not None
                        changed = sum(count for count, color in colors if color != (0, 0, 0))
                    check = {'context': name, 'policy': policy, 'order': order,
                        'scheduled_seconds': delay, 'actual_seconds': time.monotonic() - started,
                        'current': current, 'dom_unchanged': await channel.read(channel.bound_frame(), ctx) == original_view,
                        'expected_sha256': captured.frame.image_sha256, 'current_sha256': frames[-1]['sha256'],
                        'frame': frames[-1], 'diff_bbox': bbox, 'changed_pixels': changed,
                        'refusals': events[offset:]}
                    report['checks'].append(check)
            finally:
                errors = []
                for close in ([channel.aclose] if channel is not None else []) + [ctx.runtime.aclose]:
                    try:
                        await close()
                    except Exception as exc:
                        errors.append(type(exc).__name__)
                if server is not None:
                    server.close()
                    await server.wait_closed()
                context_row.update(cleanup_errors=errors, cleanup_confirmed=not errors and
                    (channel is None or channel.closed and (channel.browser is None or not channel.browser.is_connected())), frames=frames)
                (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
            if not context_row['cleanup_confirmed']:
                raise RuntimeError('diagnostic cleanup unconfirmed')
    if sources() != frozen['source_sha256']:
        raise ValueError('diagnostic source changed')
    return report


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run(args.output))
    print(json.dumps({'checks': len(result['checks']), 'contexts': len(result['contexts']),
        'refused': {p: sum(not c['current'] for c in result['checks'] if c['policy'] == p) for p in POLICIES},
        'model_calls': 0}))


if __name__ == '__main__':
    main()
