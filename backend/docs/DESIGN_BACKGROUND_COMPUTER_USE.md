# Background Computer Use via Virtual Desktop Isolation

## Problem

Current computer-use implementation (`tools/computer_use_macos.py`) takes over the full screen:
- `screencapture -x -C` captures the entire desktop
- `CGEventPost` moves the real cursor and types with the real keyboard
- The user cannot interact with their computer while the agent works

## Goal

Allow the computer-use agent to operate on a target application **without disturbing the user**. The user continues working on their physical display while the agent controls apps in an isolated graphical context.

## Solution: Virtual Desktop Isolation

Run the target app in a separate virtual display that the agent fully owns. The user's session is untouched — no cursor hijacking, no focus stealing, no event conflicts.

```
┌─────────────────────────────────┐  ┌─────────────────────────────────┐
│   User's Desktop (Physical)     │  │   Agent's Desktop (Virtual)     │
│                                 │  │                                 │
│  User works normally            │  │  Target app runs here           │
│  Mouse/keyboard belong to user  │  │  Agent has its own cursor       │
│  No interference                │  │  Full CGEvent works (app is     │
│                                 │  │  "foreground" in this session)  │
└─────────────────────────────────┘  └─────────────────────────────────┘
         ▲                                       ▲
         │                                       │
    User interacts                     Agent captures screenshots
    normally                           and posts input events
                                       (standard public APIs)
```

## Why Virtual Display Isolation Solves All Problems

| Problem | Why it's solved |
|---------|----------------|
| Screenshot capture | Standard `screencapture` or ScreenCaptureKit works — app IS foreground in its session |
| Input injection | Standard `CGEventPost` works — no "untrusted event" rejection |
| Chromium/Electron apps | No special handling — receives real HID-like events with genuine focus |
| API stability | Only public, documented APIs — no SkyLight breakage risk across macOS versions |
| Parallelism | Spin up N virtual displays for N agents on N apps simultaneously |
| User disruption | Zero — physical display is completely separate |

## Implementation Options

### Option A: `CGVirtualDisplay` (Recommended)

Available since macOS 14. Creates a virtual screen with no physical monitor.

**Pros:**
- Lightweight (no separate user account)
- ScreenCaptureKit can capture it
- Standard CGEvents work within its coordinate space
- App Store eligible (public API)

**Cons:**
- macOS 14+ only
- Requires understanding of display routing for app launch

**Architecture:**
1. Swift/Rust helper creates a `CGVirtualDisplay` at fixed resolution (e.g., 1920x1080)
2. Target app is launched and routed to the virtual display
3. ScreenCaptureKit captures frames scoped to that display
4. CGEvents are posted targeting the virtual display's coordinate space
5. Screenshots are piped to the vision model; actions are posted back

### Option B: Separate macOS User Session

Fast-user-switching with a headless agent user account.

**Pros:**
- Complete isolation (separate login session)
- No display routing complexity
- Works on older macOS versions

**Cons:**
- Requires creating a system user account
- Heavier resource usage
- Needs admin privileges to set up
- Not App Store eligible

### Option C: Separate macOS Space

Move target app to a different Space, capture via ScreenCaptureKit.

**Pros:**
- Simplest to implement
- No extra users or virtual displays

**Cons:**
- `CGEventPost` goes to the active Space by default — input routing is unreliable
- Spaces aren't truly separate sessions
- Weakest isolation

## Recommendation

**Option A (`CGVirtualDisplay`)** is the sweet spot:
- Public API, stable across macOS updates
- Lighter than a separate user session
- Full input/output isolation
- Supports parallel agents

## Implementation Plan

### Phase 1: Virtual Display Manager (Rust/Swift helper)

A small binary (or Tauri sidecar) that:
- Creates a `CGVirtualDisplay` with configurable resolution
- Returns the display ID for ScreenCaptureKit targeting
- Manages lifecycle (create, destroy, list active displays)

```swift
import CoreGraphics

let descriptor = CGVirtualDisplayDescriptor()
descriptor.size = CGSize(width: 1920, height: 1080)
descriptor.hiDPI = false
let display = CGVirtualDisplay(descriptor: descriptor)
```

### Phase 2: App Launcher

Routes the target app to the virtual display:
- Use `NSWorkspace` with display assignment
- Or launch via `open` with display affinity flags
- Ensure the app's windows land on the virtual display

### Phase 3: Screenshot Capture (ScreenCaptureKit)

Replace current `screencapture -x -C` with display-scoped capture:

```swift
let filter = SCContentFilter(display: virtualDisplay, excludingWindows: [])
let config = SCStreamConfiguration()
config.width = 1920
config.height = 1080
// Capture single frame
```

### Phase 4: Input Injection

Post CGEvents to the virtual display's coordinate space:

```swift
let event = CGEvent(mouseEventSource: nil,
                    mouseType: .leftMouseDown,
                    mouseCursorPosition: CGPoint(x: x, y: y),
                    mouseButton: .left)
// Target the virtual display
event?.post(tap: .cghidEventTap)
```

The key difference: since the target app has genuine focus on the virtual display, standard `CGEventPost` works without any private API workarounds.

### Phase 5: Integration with Tank Agent

Wire the virtual display pipeline into the existing `ComputerUseMacOS` tool:
- `screenshot()` → captures from virtual display instead of physical
- `click(x, y)` → posts to virtual display coordinate space
- `type_text(text)` → posts key events to virtual display
- Add `target_app: str` parameter to specify which app to control
- Add lifecycle management (create display on first use, destroy on session end)

## Alternative Approaches Considered

### Private SkyLight APIs (What Cua Driver Does)

Uses `SLPSPostEventRecordTo` to post events directly to a process without focus change.

- Works today but uses undocumented private APIs
- Can break on any macOS update
- Requires "focus-without-raise" hack for Chromium
- Requires "primer click" at (-1,-1) for untrusted event workaround
- Not App Store eligible

Rejected because: fragile, undocumented, requires per-app workarounds.

### XSendEvent on Linux

On X11, `XSendEvent` can target any window. But:
- Chromium/Firefox check the `send_event` flag and reject synthetic events
- Wayland makes this impossible by design (no cross-client input injection)
- Only relevant for Linux deployment (not our primary target)

## Research References

- **Cua Driver** (github.com/trycua/cua) — open-source background automation using SkyLight
- **OpenAI Codex** — uses virtual desktop isolation for background computer use
- **ScreenCaptureKit** — Apple's modern per-window/per-display capture API (WWDC22)
- **CGVirtualDisplay** — Apple's virtual display API (macOS 14+)

## Constraints

- Minimized windows cannot be captured by any macOS API (window server stops compositing them)
- Virtual display approach requires macOS 14+ for `CGVirtualDisplay`
- The target app must be running (not just a saved state)
- Multiple agents = multiple virtual displays = proportional memory/GPU usage
