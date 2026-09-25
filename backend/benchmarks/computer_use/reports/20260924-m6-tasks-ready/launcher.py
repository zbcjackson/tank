"""M6 item-3/4 generalized controlled launcher.

One task per invocation: `--task <id> [--live]`. Hides non-target apps behind
the controlled black background, gates pointer actions to the target apps'
windows, and runs the task's six scheduled rows (A/C x 3 alternating rounds)
or, for --task long-history, the two-row item-4 manifest (600s / 60 tools /
60 locates). Defaults to local preview; --live requires explicit user consent
and a reviewed go file after the initial screenshot.
"""
import argparse, asyncio, base64, json, os, runpy, subprocess, threading, time
from pathlib import Path
import AppKit, Quartz, objc
from PyObjCTools import AppHelper
from dotenv import load_dotenv
from tank_backend.config import AppConfig
from tank_backend.benchmarks.desktop_recovery import set_app_hidden
from tank_backend.tools import computer_use_macos as macos
from tank_backend.core.content import ImageBlock

BACKEND = Path('/Users/zbcjackson/src/tank/backend')
FREEZE = BACKEND / 'benchmarks/computer_use/reports/20260925-m6-tasks-runtime'
TASKS_PROPOSAL = BACKEND / 'benchmarks/computer_use/reports/20260925-m6-tasks-proposal/proposal.json'
LH_PROPOSAL = BACKEND / 'benchmarks/computer_use/reports/20260924-m6-longhistory-proposal/proposal.json'
# Controlled scope per task: the only regular apps allowed on screen.
TASK_APPS = {
    'open-settings': ['System Settings'],
    'browser-navigate': ['Safari'], 'local-form': ['Safari'],
    'typing-fidelity': ['Safari'], 'links-history': ['Safari'],
    'small-text-code': ['Safari'],
    'file-ops': ['Finder'], 'multi-select-copy': ['Finder'], 'drag-file': ['Finder'],
    'terminal-write': ['Terminal'],
    'settings-toggle': ['System Settings'],
    'editor-save': ['TextEdit'], 'window-copy': ['TextEdit', 'Safari'],
    'long-history': ['TextEdit'],
}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--live', action='store_true')
parser.add_argument('--task', choices=sorted(TASK_APPS), required=True)
args = parser.parse_args()
LIVE, TASK = args.live, args.task
APPS = TASK_APPS[TASK]
PILOT_ACCEPTANCE = 'reviewed-2026-09-24-m6-calc-and-m5-pairs'
api = runpy.run_path(str(BACKEND / 'scripts/prepare_computer_batch.py'))
if TASK == 'long-history':
    api['preflight_m6_longhistory'](FREEZE, LH_PROPOSAL)
else:
    api['preflight_m6_tasks'](FREEZE, TASKS_PROPOSAL)
OUT = Path(f'/tmp/tank-m6-{TASK}-20260925-' + ('live' if LIVE else 'preview'))
OUT.mkdir(exist_ok=False)
app = AppKit.NSApplication.sharedApplication()
app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
workspace = AppKit.NSWorkspace.sharedWorkspace()
original_front = workspace.frontmostApplication()
original_mouse = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
terminal_names_before = set()
if TASK == 'terminal-write' and subprocess.run(['pgrep', '-x', 'Terminal'],
                                               capture_output=True).returncode == 0:
    # Only query when Terminal already runs: `tell application "Terminal"`
    # on a not-running Terminal would launch it (slow, opens a window).
    try:
        listed = subprocess.run(['osascript', '-e',
                                 'tell application "Terminal" to get name of every window'],
                                capture_output=True, text=True, timeout=10)
        terminal_names_before = {n.strip() for n in listed.stdout.split(',') if n.strip()}
    except subprocess.TimeoutExpired:
        terminal_names_before = set()
# Safari EULA: the container is TCC-protected, so the EULA is accepted once
# by the operator (recorded in the README) instead of scripted here.
hidden = []
for other in workspace.runningApplications():
    if (other.activationPolicy() == AppKit.NSApplicationActivationPolicyRegular
            and not other.isHidden()
            and str(other.localizedName()) not in APPS
            and other.processIdentifier() != os.getpid()):
        if set_app_hidden(other, True):
            hidden.append(other)
screen = next(s for s in AppKit.NSScreen.screens()
              if int(s.deviceDescription()['NSScreenNumber']) == int(Quartz.CGMainDisplayID()))
window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
    screen.frame(), AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False)
window.setBackgroundColor_(AppKit.NSColor.blackColor()); window.setOpaque_(True)
window.setHidesOnDeactivate_(False); window.setCanHide_(False)
window.setTitle_('Tank M6 controlled background'); window.orderFrontRegardless()
clipboard = AppKit.NSPasteboard.generalPasteboard()
saved_clipboard = [[(str(t), bytes(item.dataForType_(t))) for t in item.types()
                    if item.dataForType_(t) is not None]
                   for item in (clipboard.pasteboardItems() or [])]
gate_events = []


def allowed_window_rects():
    """On-screen layer-0 windows of the task's target apps, main display."""
    display = next(s for s in AppKit.NSScreen.screens()
                   if int(s.deviceDescription()['NSScreenNumber']) == int(Quartz.CGMainDisplayID()))
    width, height = int(display.frame().size.width), int(display.frame().size.height)
    info = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly,
                                             Quartz.kCGNullWindowID)
    rects = []
    for entry in info or []:
        if entry.get('kCGWindowOwnerName') not in APPS or entry.get('kCGWindowLayer') != 0:
            continue
        bounds = entry.get('kCGWindowBounds') or {}
        x, y, w, h = (int(bounds.get(k, -1)) for k in ('X', 'Y', 'Width', 'Height'))
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
            continue
        rects.append((x, y, x + w, y + h))
    return rects


def inside_any(point, rects):
    return any(l <= point[0] <= r and t <= point[1] <= b for l, t, r, b in rects)


def gate_action(point):
    rects = allowed_window_rects()
    if inside_any(point, rects):
        return None, None
    reason = ('click target ' + str(tuple(point)) + ' is outside the task windows '
              + str(rects) + '; the estimate is wrong or the target app is not '
              'frontmost - observe again and answer in the declared unit')
    gate_events.append({'point': [int(point[0]), int(point[1])],
                        'containers': [list(r) for r in rects], 'landed': 'outside'})
    return None, reason


original_click = macos._click_macos
original_drag = macos._drag_macos


def gated_click(x, y, button='left', clicks=1):
    _, reason = gate_action((x, y))
    if reason:
        raise RuntimeError('input blocked: ' + reason)
    return original_click(x, y, button, clicks)


def gated_drag(x1, y1, x2, y2, button='left'):
    _, reason = gate_action((x1, y1))
    if reason:
        raise RuntimeError('input blocked: ' + reason)
    _, reason = gate_action((x2, y2))
    if reason:
        raise RuntimeError('input blocked: ' + reason)
    return original_drag(x1, y1, x2, y2, button)


macos._click_macos = gated_click
macos._drag_macos = gated_drag
original_capture = macos._capture_screenshot_macos


def scope_violations():
    visible = [a for a in workspace.runningApplications()
               if a.activationPolicy() == AppKit.NSApplicationActivationPolicyRegular
               and not a.isHidden() and str(a.localizedName()) not in APPS
               and a.processIdentifier() != os.getpid()]
    on_screen = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly,
                                                  Quartz.kCGNullWindowID)
    background_visible = any(int(w.get('kCGWindowNumber', -1)) == int(window.windowNumber())
                             for w in on_screen)
    return visible, background_visible


def pump_runloop(seconds=.4):
    AppKit.NSRunLoop.currentRunLoop().runUntilDate_(
        AppKit.NSDate.dateWithTimeIntervalSinceNow_(seconds))


def reassert_scope():
    """Hide what reappeared; never activate a target app (no pre-fulfilment)."""
    rehidden = 0
    for other in workspace.runningApplications():
        if (other.activationPolicy() == AppKit.NSApplicationActivationPolicyRegular
                and not other.isHidden() and str(other.localizedName()) not in APPS
                and other.processIdentifier() != os.getpid()):
            if set_app_hidden(other, True):
                hidden.append(other); rehidden += 1
    pump_runloop(.3)
    return rehidden


def check_scope():
    visible, background_visible = scope_violations()
    if visible or not background_visible:
        print('scope drift; reasserting fixture (hide only, no activation)', flush=True)
        reassert_scope()
        visible, background_visible = scope_violations()
    if visible:
        raise RuntimeError('Controlled screenshot scope changed; no image sent; visible='
                           + repr([str(a.bundleIdentifier()) for a in visible]))
    if not background_visible:
        raise RuntimeError('Controlled background is not visible; no image sent')


def capture(*, include_cursor=True):
    reassert_scope(); check_scope()
    image = original_capture(include_cursor=include_cursor)
    check_scope()
    return image


macos._capture_screenshot_macos = capture


async def pilot():
    # Give the fixture a moment to settle; the agent launches the target app.
    await asyncio.sleep(1)
    shot = await macos.ScreenshotTool().execute()
    if shot.error:
        raise RuntimeError(str(shot.content))
    block = next(b for b in shot.content if isinstance(b, ImageBlock))
    (OUT / 'initial.png').write_bytes(base64.b64decode(block.source.split(',', 1)[1]))
    (OUT / 'ready.json').write_text(json.dumps({
        'model_requests': 0, 'scope': 'controlled desktop for task ' + TASK,
        'allowed_apps': APPS, 'task': TASK,
        'rows': 2 if TASK == 'long-history' else 6}))
    if not LIVE:
        print('Preview only: zero model requests; task=' + TASK
              + ' allowed apps: ' + json.dumps(APPS), flush=True)
        return
    for _ in range(240):
        if (OUT / 'go').exists():
            break
        await asyncio.sleep(.5)
    else:
        raise RuntimeError('Local screenshot review deadline expired; no model call')
    check_scope()
    load_dotenv(BACKEND / 'core/.env')
    source = AppConfig.load(BACKEND / 'core/config.yaml')
    key = source.llm_profiles['computer_use'].api_key
    if not key:
        raise RuntimeError('Missing provider credential')
    os.environ['M5_DASHSCOPE_API_KEY'] = key
    if TASK == 'long-history':
        results = await api['execute_m6_longhistory'](
            FREEZE, LH_PROPOSAL, OUT / 'trials', live_authorized=True,
            pilot_acceptance=PILOT_ACCEPTANCE)
    else:
        results = await api['execute_m6_task_trials'](
            FREEZE, TASKS_PROPOSAL, OUT / 'trials', task_id=TASK,
            live_authorized=True, pilot_acceptance=PILOT_ACCEPTANCE)
    for result in results:
        print(json.dumps({'completed': result['completed'],
                          'spend': result['spend']['batch'],
                          'stop_reason': result['spend']['stop_reason']}), flush=True)


error = []


def finish():
    cleanup = {}
    try:
        if TASK == 'terminal-write':
            # Close only Terminal windows the trial opened, never the user's.
            names = ','.join(json.dumps(n) for n in sorted(terminal_names_before))
            subprocess.run(['osascript', '-e',
                            'tell application "Terminal" to close (every window '
                            'whose name is not in {' + names + '})'],
                           capture_output=True, timeout=10)
        cleanup['pressed_keys'] = [i for i in range(128) if Quartz.CGEventSourceKeyState(
            Quartz.kCGEventSourceStateCombinedSessionState, i)]
        cleanup['pressed_mouse_buttons'] = [i for i in range(3) if Quartz.CGEventSourceButtonState(
            Quartz.kCGEventSourceStateCombinedSessionState, i)]
        window.close(); cleanup['background_closed'] = not window.isVisible()
        cleanup['hidden_apps_restored'] = all(set_app_hidden(other, False) for other in hidden)
        items = []
        for values in saved_clipboard:
            item = AppKit.NSPasteboardItem.alloc().init()
            for kind, data in values:
                item.setData_forType_(data, kind)
            items.append(item)
        clipboard.clearContents()
        cleanup['clipboard_restored'] = bool(clipboard.writeObjects_(items)) if items else True
        Quartz.CGWarpMouseCursorPosition(original_mouse)
        restored = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        cleanup['cursor_restored'] = (abs(restored.x - original_mouse.x) <= 1
                                      and abs(restored.y - original_mouse.y) <= 1)
        if original_front is not None:
            original_front.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        cleanup['worker_finished'] = True
        cleanup['gate_blocked'] = gate_events
        (OUT / 'cleanup.json').write_text(json.dumps(cleanup, indent=2))
    finally:
        app.stop_(None)
        event = AppKit.NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            AppKit.NSEventTypeApplicationDefined, (0, 0), 0, 0, 0, None, 0, 0, 0)
        app.postEvent_atStart_(event, True)


def worker():
    with objc.autorelease_pool():
        try:
            asyncio.run(pilot())
        except Exception as exc:
            error.append(type(exc).__name__)
            (OUT / 'error.txt').write_text(str(exc))
            print('Launcher stopped: ' + str(exc), flush=True)
        finally:
            AppHelper.callAfter(finish)


thread = threading.Thread(target=worker, daemon=True)
thread.start()
app.run()
thread.join(timeout=3)
if error:
    raise SystemExit(1)
