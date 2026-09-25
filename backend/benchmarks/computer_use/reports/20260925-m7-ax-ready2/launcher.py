"""Defaults to local preview. --live requires explicit user consent and a reviewed go file."""
import argparse, asyncio, base64, hashlib, json, os, runpy, subprocess, threading, time
from pathlib import Path
import AppKit, Quartz, objc
from PyObjCTools import AppHelper
from dotenv import load_dotenv
from tank_backend.config import AppConfig
from tank_backend.benchmarks.batch import BatchTrial, run_batch
from tank_backend.benchmarks.comparison_contract import ComparisonContract
from tank_backend.benchmarks.desktop_recovery import set_app_hidden
from tank_backend.benchmarks.frozen_inputs import FrozenFile, FrozenInputs
from tank_backend.benchmarks.request_budget import RequestLimits
from tank_backend.benchmarks.spend_ledger import SpendLimit
from tank_backend.benchmarks.calc_validator import reset_calculator
from tank_backend.tools import computer_use_macos as macos
from tank_backend.core.content import ImageBlock

BACKEND=Path('/Users/zbcjackson/src/tank/backend')
FREEZE=BACKEND/'benchmarks/computer_use/reports/20260925-m7-ax-runtime2'
PROPOSAL=BACKEND/'benchmarks/computer_use/reports/20260925-m7-ax-proposal2/proposal.json'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--live',action='store_true')
args=parser.parse_args(); LIVE=args.live
PILOT_ACCEPTANCE='reviewed-2026-09-25-m7-live1-host-window-binding-fix'
api=runpy.run_path(str(BACKEND/'scripts/prepare_computer_batch.py'))
api['preflight_m7_ax'](FREEZE,PROPOSAL)
OUT=Path('/tmp/tank-m7-ax2-20260925-'+('live' if LIVE else 'preview')); OUT.mkdir(exist_ok=False)
app=AppKit.NSApplication.sharedApplication(); app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
workspace=AppKit.NSWorkspace.sharedWorkspace(); original_front=workspace.frontmostApplication()
original_mouse=Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
hidden=[]
for other in workspace.runningApplications():
    if other.activationPolicy()==AppKit.NSApplicationActivationPolicyRegular and not other.isHidden() and other.bundleIdentifier() not in ('com.apple.calculator',) and other.processIdentifier()!=os.getpid():
        # AppKit dispatches hide requests through this run loop, and the BOOL
        # return is False on macOS 26 even on success: pump and verify state.
        if set_app_hidden(other, True): hidden.append(other)
screen=next(s for s in AppKit.NSScreen.screens() if int(s.deviceDescription()['NSScreenNumber'])==int(Quartz.CGMainDisplayID()))
window=AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(screen.frame(), AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False)
window.setBackgroundColor_(AppKit.NSColor.blackColor()); window.setOpaque_(True)
window.setHidesOnDeactivate_(False); window.setCanHide_(False)
window.setTitle_('Tank M7 controlled background'); window.orderFrontRegardless()
clipboard=AppKit.NSPasteboard.generalPasteboard()
saved_clipboard=[[(str(t),bytes(item.dataForType_(t))) for t in item.types() if item.dataForType_(t) is not None] for item in (clipboard.pasteboardItems() or [])]
# --- controlled-window gate -------------------------------------------------
# Measurement guard: a pointer action outside the target window is either a
# scale/unit confusion or a gross estimate error. Dispatching it silently lands
# on the backdrop, which then covers the target (4 of 8 live pilots). Reject it
# instead, so no input is sent and the model gets an explicit reason.
gate_events=[]

def controlled_window_rect():
    """Current Calculator window on the main display as (l,t,r,b), or None."""
    display=next(s for s in AppKit.NSScreen.screens() if int(s.deviceDescription()['NSScreenNumber'])==int(Quartz.CGMainDisplayID()))
    width,height=int(display.frame().size.width),int(display.frame().size.height)
    info=Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly,Quartz.kCGNullWindowID)
    for entry in info or []:
        if entry.get('kCGWindowOwnerName')!='Calculator':
            continue
        bounds=entry.get('kCGWindowBounds') or {}
        x,y,w,h=(int(bounds.get(k,-1)) for k in ('X','Y','Width','Height'))
        if x<0 or y<0 or w<=0 or h<=0 or x+w>width or y+h>height:
            continue
        return (x,y,x+w,y+h)
    return None

# Declared unit of the most recent parsed answer; both the integrated and the
# split paths parse through GroundingAdapter, so one hook records it.
LAST_PROTOCOL={'value':None}

def display_size():
    display=next(s for s in AppKit.NSScreen.screens() if int(s.deviceDescription()['NSScreenNumber'])==int(Quartz.CGMainDisplayID()))
    return (int(display.frame().size.width),int(display.frame().size.height))

def inside(point,container):
    left,top,right,bottom=container
    return left<=point[0]<=right and top<=point[1]<=bottom

def disambiguate_unit(point,container):
    """Recover a unit-confused answer using the controlled window as the filter.

    Only for pixel contracts, and only when the point could itself be a 0..1000
    value (that is the signature of a normalized answer in a pixel field). The
    corrected point must land inside the window, so a plain miss is never moved.
    """
    if container is None or LAST_PROTOCOL['value']!='pixels' or inside(point,container):
        return None
    if not (0<=point[0]<=1000 and 0<=point[1]<=1000):
        return None
    width,height=display_size()
    corrected=(round(point[0]*width/1000),round(point[1]*height/1000))
    return corrected if inside(corrected,container) else None

def gate_decision(point,container):
    """('use',point) to dispatch, ('block',reason) to refuse, None to pass through."""
    if container is None:
        return ('block','target window is not on screen; observe again before acting')
    if inside(point,container):
        return None
    corrected=disambiguate_unit(point,container)
    if corrected is not None:
        return ('use',corrected)
    return ('block','click target '+str(tuple(point))+' is outside the controlled window '+
            str(container)+'; the estimate is in the wrong place or the wrong coordinate unit - '+
            'observe again and answer with the declared unit')

def gate_action(point):
    """Decide and log one pointer target; returns the corrected point or a reason."""
    container=controlled_window_rect()
    verdict=gate_decision(point,container)
    if verdict is None:
        return None,None
    kind,value=verdict
    event={'point':[int(point[0]),int(point[1])],
           'container':list(container) if container else None,'landed':'outside'}
    if kind=='use':
        event['unit_disambiguated']=list(value)
        gate_events.append(event)
        return value,None
    gate_events.append(event)
    return None,value

from tank_backend.tools.computer_grounding import GroundingAdapter
_original_parse_response=GroundingAdapter.parse_response
def recorded_parse_response(self,response,size):
    LAST_PROTOCOL['value']=getattr(self,'protocol',None)
    return _original_parse_response(self,response,size)
GroundingAdapter.parse_response=recorded_parse_response

original_click=macos._click_macos
original_drag=macos._drag_macos

def gated_click(x,y,button="left",clicks=1):
    corrected,reason=gate_action((x,y))
    if reason:
        raise RuntimeError('input blocked: '+reason)
    if corrected is not None:
        print('gate: unit-disambiguated '+str((x,y))+' -> '+str(corrected),flush=True)
        x,y=corrected
    return original_click(x,y,button,clicks)

def gated_drag(x1,y1,x2,y2,button="left"):
    corrected,reason=gate_action((x1,y1))
    if reason:
        raise RuntimeError('input blocked: '+reason)
    if corrected is not None:
        print('gate: unit-disambiguated start '+str((x1,y1))+' -> '+str(corrected),flush=True)
        x1,y1=corrected
    corrected,reason=gate_action((x2,y2))
    if reason:
        raise RuntimeError('input blocked: '+reason)
    if corrected is not None:
        print('gate: unit-disambiguated end '+str((x2,y2))+' -> '+str(corrected),flush=True)
        x2,y2=corrected
    return original_drag(x1,y1,x2,y2,button)

macos._click_macos=gated_click
macos._drag_macos=gated_drag

original_capture=macos._capture_screenshot_macos

def scope_violations(workspace,window):
    visible=[a for a in workspace.runningApplications() if a.activationPolicy()==AppKit.NSApplicationActivationPolicyRegular and not a.isHidden() and a.bundleIdentifier() not in ('com.apple.calculator',) and a.processIdentifier()!=os.getpid()]
    on_screen=Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly,Quartz.kCGNullWindowID)
    background_visible=window is not None and any(int(w.get('kCGWindowNumber',-1))==int(window.windowNumber()) for w in on_screen)
    return visible,background_visible

def pump_runloop(seconds=.4):
    AppKit.NSRunLoop.currentRunLoop().runUntilDate_(AppKit.NSDate.dateWithTimeIntervalSinceNow_(seconds))

def reassert_scope():
    """Re-establish the controlled fixture: target app frontmost, others hidden.

    The task teardown kills Calculator between trials, and with no regular app
    foreground Finder reappears on its own; hiding alone cannot win that race,
    so activate the target first and then hide what is left visible.
    """
    subprocess.run(['osascript','-e','tell application "Calculator" to activate'],capture_output=True,timeout=20)
    pump_runloop(.6)
    rehidden=0
    for other in workspace.runningApplications():
        if other.activationPolicy()==AppKit.NSApplicationActivationPolicyRegular and not other.isHidden() and other.bundleIdentifier() not in ('com.apple.calculator',) and other.processIdentifier()!=os.getpid():
            if set_app_hidden(other, True):
                hidden.append(other); rehidden+=1
    pump_runloop(.3)
    return rehidden

def check_scope():
    visible,background_visible=scope_violations(workspace,window)
    if visible or not background_visible:
        print('scope drift; reasserting fixture (target app gets activated)',flush=True)
        reassert_scope()
        visible,background_visible=scope_violations(workspace,window)
    if visible: raise RuntimeError('Controlled screenshot scope changed; no image sent; visible='+repr([str(a.bundleIdentifier()) for a in visible]))
    if not background_visible: raise RuntimeError('Controlled background is not visible; no image sent')

def capture(*, include_cursor=True):
    reassert_scope(); check_scope(); image=original_capture(include_cursor=include_cursor); check_scope(); return image
macos._capture_screenshot_macos=capture

async def pilot():
    subprocess.run(['osascript','-e','tell application "Calculator" to activate'],check=True,capture_output=True,timeout=20)
    await asyncio.sleep(1)
    # Finder may become visible again while no regular app is foreground.
    # Hide it only after Calculator is active, then let AppKit update its state.
    for other in workspace.runningApplications():
        if other.bundleIdentifier() == 'com.apple.finder' and not other.isHidden():
            if set_app_hidden(other, True): hidden.append(other)
    await asyncio.sleep(.3)
    subprocess.run(['osascript','-e','tell application "System Events" to tell process "Calculator" to set position of window 1 to {600, 100}'],check=True,capture_output=True,timeout=20)
    if not reset_calculator(): raise RuntimeError('Calculator reset failed before model admission')
    subprocess.run(['osascript','-e','tell application "System Events" to tell process "Calculator" to set position of window 1 to {600, 100}'],check=True,capture_output=True,timeout=20)
    shot=await macos.ScreenshotTool().execute()
    if shot.error: raise RuntimeError(str(shot.content))
    block=next(b for b in shot.content if isinstance(b,ImageBlock))
    (OUT/'initial.png').write_bytes(base64.b64decode(block.source.split(',',1)[1]))
    (OUT/'ready.json').write_text(json.dumps({'model_requests':0,'scope':'controlled Calculator desktop','phase':'m7-ax-pairs','enforce_agent_budget':True,'trials':9}))
    if not LIVE:
        scheduled=[row['key'] for row in json.loads(PROPOSAL.read_text())['trials']
                   if row['phase'] in ('m7-pair-1','m7-pair-2','m7-pair-3')]
        print('Preview only: zero model requests; scheduled core trials: '+json.dumps(scheduled),flush=True)
        return
    for _ in range(240):
        if (OUT/'go').exists(): break
        await asyncio.sleep(.5)
    else: raise RuntimeError('Local screenshot review deadline expired; no model call')
    check_scope()
    load_dotenv(BACKEND/'core/.env')
    source=AppConfig.load(BACKEND/'core/config.yaml')
    key=source.llm_profiles['computer_use'].api_key
    if not key: raise RuntimeError('Missing provider credential')
    os.environ['M5_DASHSCOPE_API_KEY']=key
    results=await api['execute_m7_ax_trials'](FREEZE,PROPOSAL,OUT/'trials',live_authorized=True,
                                                 pilot_acceptance=PILOT_ACCEPTANCE)
    for result in results:
        print(json.dumps({'completed':result['completed'],
                          'spend':result['spend']['batch'],
                          'stop_reason':result['spend']['stop_reason']}),flush=True)

error=[]
def finish():
    cleanup={}
    try:
        subprocess.run(['osascript','-e','tell application "Calculator" to quit'],capture_output=True,timeout=20)
        time.sleep(.5)
        cleanup['calculator_closed']=not any(a.bundleIdentifier()=='com.apple.calculator' for a in workspace.runningApplications())
        cleanup['pressed_keys']=[i for i in range(128) if Quartz.CGEventSourceKeyState(Quartz.kCGEventSourceStateCombinedSessionState,i)]
        cleanup['pressed_mouse_buttons']=[i for i in range(3) if Quartz.CGEventSourceButtonState(Quartz.kCGEventSourceStateCombinedSessionState,i)]
        window.close(); cleanup['background_closed']=not window.isVisible()
        cleanup['hidden_apps_restored']=all(set_app_hidden(other, False) for other in hidden)
        items=[]
        for values in saved_clipboard:
            item=AppKit.NSPasteboardItem.alloc().init()
            for kind,data in values: item.setData_forType_(data,kind)
            items.append(item)
        clipboard.clearContents()
        cleanup['clipboard_restored']=bool(clipboard.writeObjects_(items)) if items else True
        Quartz.CGWarpMouseCursorPosition(original_mouse)
        restored_mouse=Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        cleanup['cursor_restored']=abs(restored_mouse.x-original_mouse.x)<=1 and abs(restored_mouse.y-original_mouse.y)<=1
        if original_front is not None: original_front.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        cleanup['worker_finished']=True
        cleanup['gate_blocked']=gate_events
        (OUT/'cleanup.json').write_text(json.dumps(cleanup,indent=2))
    finally:
        app.stop_(None)
        event=AppKit.NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(AppKit.NSEventTypeApplicationDefined,(0,0),0,0,0,None,0,0,0)
        app.postEvent_atStart_(event,True)

def worker():
    with objc.autorelease_pool():
        try: asyncio.run(pilot())
        except Exception as exc:
            error.append(type(exc).__name__)
            (OUT/'error.txt').write_text(str(exc))
            print('Pilot stopped: '+str(exc),flush=True)
        finally: AppHelper.callAfter(finish)
thread=threading.Thread(target=worker,daemon=True);thread.start();app.run();thread.join(timeout=3)
if error: raise SystemExit(1)
