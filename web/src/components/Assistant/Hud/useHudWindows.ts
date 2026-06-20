import { useEffect, useMemo, useRef, useState } from 'react';
import type { Step, ToolContent } from '../../../types/message';
import type { HudWindowDescriptor, HudWindowType, HudWindowState } from './types';

const LINGER_MS: Record<HudWindowType, number> = {
  thinking: 1300,
  tool: 1500,
  agent: 1700,
  response: 0,
};

const CLOSE_ANIM_MS = 540;

const SAFE_ZONE_X = 360;
const SAFE_ZONE_Y = 240;
const APPROX_WIN_W: Record<HudWindowType, number> = {
  thinking: 400,
  tool: 400,
  agent: 400,
  response: 540,
};
const APPROX_WIN_H = 200;
const CASCADE_OFFSET = { x: 26, y: 22 };

interface WindowEntry {
  descriptor: HudWindowDescriptor;
  /** Tracks the linger timer so we can cancel it if a new chunk arrives. */
  lingerTimer: number | null;
  /** Tracks the remove-after-close-animation timer. */
  removeTimer: number | null;
  /** Cascade slot, used to compute deterministic positions per type. */
  slot: number;
  /**
   * For response windows: latches true the first time TTS playback is detected
   * (`isSpeaking` becomes true) for this window. Used to gate close on audio
   * having actually played at least once.
   */
  hasStartedSpeaking: boolean;
}

interface UseHudWindowsOptions {
  /** Latest assistant Step stream from useAssistant. */
  steps: Step[];
  /** True when the assistant is actively speaking — keeps response window open. */
  isSpeaking: boolean;
  /** True when the assistant is doing anything other than idle. */
  isActive: boolean;
}

interface UseHudWindowsResult {
  windows: HudWindowDescriptor[];
  /** Number of currently-open (non-closing) windows. */
  openCount: number;
  /** Tone derived from the most recently active window. */
  activeTone: 'idle' | 'thinking' | 'tool' | 'agent' | 'response';
  /** Brain readout for the bottom-left chrome. */
  brainStatusLabel: string;
  /** Per-window z-order. */
  zOrder: Record<string, number>;
  raiseWindow: (id: string) => void;
}

function isAgentTool(content: ToolContent): boolean {
  // Backend exposes the subagent dispatcher as a regular tool named 'agent'.
  return content.name === 'agent';
}

function deriveSubagentType(content: ToolContent): string {
  try {
    const parsed: unknown = JSON.parse(content.arguments || '{}');
    if (parsed && typeof parsed === 'object' && 'subagent_type' in parsed) {
      const v = (parsed as Record<string, unknown>).subagent_type;
      if (typeof v === 'string' && v) return v;
    }
  } catch {
    // arguments may be partial / non-JSON during streaming
  }
  return 'subagent';
}

function deriveSubagentTask(content: ToolContent): string {
  try {
    const parsed: unknown = JSON.parse(content.arguments || '{}');
    if (parsed && typeof parsed === 'object') {
      const obj = parsed as Record<string, unknown>;
      const desc = obj.description;
      if (typeof desc === 'string' && desc) return desc;
      const prompt = obj.prompt;
      if (typeof prompt === 'string' && prompt) return prompt;
    }
  } catch {
    // ignore parse errors during streaming
  }
  return '';
}

function parseToolArgs(content: ToolContent): Array<[string, string]> {
  try {
    const parsed: unknown = JSON.parse(content.arguments || '{}');
    if (parsed && typeof parsed === 'object') {
      const obj = parsed as Record<string, unknown>;
      return Object.entries(obj).map(([k, v]) => [k, formatArgValue(v)]);
    }
  } catch {
    // partial JSON during streaming — show the raw text
  }
  if (content.arguments) {
    return [['args', content.arguments.slice(0, 200)]];
  }
  return [];
}

function formatArgValue(v: unknown): string {
  if (typeof v === 'string') return JSON.stringify(v);
  if (v === null || typeof v !== 'object') return String(v);
  return JSON.stringify(v);
}

function classifyStep(step: Step): { type: HudWindowType; id: string } | null {
  if (step.role !== 'assistant') return null;
  if (step.type === 'thinking') return { type: 'thinking', id: step.id };
  if (step.type === 'tool') {
    const content = step.content as ToolContent;
    return { type: isAgentTool(content) ? 'agent' : 'tool', id: step.id };
  }
  if (step.type === 'text' && typeof step.content === 'string' && step.content.length > 0) {
    return { type: 'response', id: step.id };
  }
  return null;
}

function statusFor(type: HudWindowType, state: HudWindowState, toolStatus?: string): string {
  if (state === 'done') return 'done';
  if (state === 'error') return 'error';
  if (type === 'tool' || type === 'agent') {
    if (toolStatus === 'executing') return 'executing';
    if (toolStatus === 'success') return 'done';
    if (toolStatus === 'error') return 'error';
    return 'calling';
  }
  if (type === 'response') return 'speaking';
  return 'running';
}

function titleFor(type: HudWindowType, step: Step): string {
  if (type === 'thinking') return 'THINKING';
  if (type === 'response') return 'RESPONSE';
  if (type === 'tool') {
    const tc = step.content as ToolContent;
    return tc.name ? `TOOL · ${tc.name}` : 'TOOL';
  }
  // agent
  const tc = step.content as ToolContent;
  const sub = deriveSubagentType(tc);
  return `AGENT · ${sub}`;
}

function bodyFor(
  type: HudWindowType,
  step: Step,
  streaming: boolean,
): HudWindowDescriptor['body'] {
  if (type === 'thinking') {
    return {
      kind: 'thinking',
      text: typeof step.content === 'string' ? step.content : '',
      streaming,
    };
  }
  if (type === 'response') {
    return {
      kind: 'response',
      text: typeof step.content === 'string' ? step.content : '',
      streaming,
    };
  }
  if (type === 'tool') {
    const tc = step.content as ToolContent;
    return {
      kind: 'tool',
      toolName: tc.name,
      args: parseToolArgs(tc),
      output: tc.result ?? null,
      streaming,
    };
  }
  // agent
  const tc = step.content as ToolContent;
  return {
    kind: 'agent',
    subagentType: deriveSubagentType(tc),
    task: deriveSubagentTask(tc),
    activities: tc.activities ?? [],
    summary: tc.result ?? '',
    summaryStreaming: streaming && !tc.result,
  };
}

function deriveState(type: HudWindowType, step: Step, isSpeaking: boolean): HudWindowState {
  if (type === 'thinking') {
    return step.isFinal ? 'done' : 'running';
  }
  if (type === 'response') {
    if (step.isFinal && !isSpeaking) return 'done';
    return 'running';
  }
  // tool / agent
  const tc = step.content as ToolContent;
  if (tc.status === 'success') return 'done';
  if (tc.status === 'error') return 'error';
  return 'running';
}

// Whether the underlying step is still producing output. Distinct from
// `deriveState` which can return 'running' for a finished response while
// TTS is still speaking — we don't want that exception to pull historical
// response steps back to life.
function isStepActive(type: HudWindowType, step: Step): boolean {
  if (type === 'thinking') return !step.isFinal;
  if (type === 'response') return !step.isFinal;
  const tc = step.content as ToolContent;
  return tc.status !== 'success' && tc.status !== 'error';
}

function cascadePosition(type: HudWindowType, slot: number): { x: number; y: number } {
  const w = typeof window !== 'undefined' ? window.innerWidth : 1280;
  const h = typeof window !== 'undefined' ? window.innerHeight : 720;
  const cx = w / 2;
  const cy = h / 2;
  const winW = APPROX_WIN_W[type];
  const winH = APPROX_WIN_H;
  const slotIdx = slot % 3;
  const dx = slotIdx * CASCADE_OFFSET.x;
  const dy = slotIdx * CASCADE_OFFSET.y;

  const clampX = (x: number) => Math.min(Math.max(20, x), Math.max(20, w - winW - 20));
  const clampY = (y: number) => Math.min(Math.max(20, y), Math.max(20, h - winH - 20));

  switch (type) {
    case 'thinking':
      return { x: clampX(cx - SAFE_ZONE_X - winW + dx), y: clampY(cy - SAFE_ZONE_Y - winH / 2 + dy) };
    case 'tool':
      return { x: clampX(cx + SAFE_ZONE_X + dx), y: clampY(cy - SAFE_ZONE_Y - winH / 2 + dy) };
    case 'agent':
      return { x: clampX(cx - SAFE_ZONE_X - winW + dx), y: clampY(cy + SAFE_ZONE_Y * 0.4 + dy) };
    case 'response':
      return { x: clampX(cx + SAFE_ZONE_X + dx), y: clampY(cy + SAFE_ZONE_Y * 0.4 + dy) };
  }
}

/**
 * Subscribes to the assistant Step stream and produces draggable HUD
 * window descriptors. Lifecycle:
 *   - First time a window-eligible step appears → open with cascade pos
 *   - Subsequent updates to the same step → patch body / state in place
 *   - Step transitions to done/final → schedule linger → schedule close
 *   - If a new chunk arrives during linger, cancel and re-open
 */
export function useHudWindows({
  steps,
  isSpeaking,
  isActive,
}: UseHudWindowsOptions): UseHudWindowsResult {
  const entriesRef = useRef<Map<string, WindowEntry>>(new Map());
  // Step IDs whose window has been opened in this session. Once a step's
  // window has been disposed, we never re-open it — even if its `isFinal`
  // flag never flipped (interrupted responses, abandoned thinking blocks).
  const disposedIdsRef = useRef<Set<string>>(new Set());
  // Marks the hook's first effect run. On first run we snapshot every
  // existing step into disposedIdsRef so chat → voice mode handoff (and any
  // mount with a non-empty step list) doesn't flash windows for the prior
  // conversation.
  const didMountRef = useRef(false);
  const slotRef = useRef<Record<HudWindowType, number>>({
    thinking: 0,
    tool: 0,
    agent: 0,
    response: 0,
  });
  const zCounterRef = useRef(100);
  const [zOrder, setZOrder] = useState<Record<string, number>>({});
  const [version, setVersion] = useState(0);

  const bump = () => setVersion((v) => v + 1);

  useEffect(() => {
    const entries = entriesRef.current;
    const seenIds = new Set<string>();

    // First-run snapshot: every step that already exists when the hook
    // mounts is treated as history. Otherwise switching chat → voice flashes
    // windows for in-progress steps that were already streaming under chat.
    // Exception: actively-running agent steps should still get HUD windows
    // so background workers are visible after mode switch.
    if (!didMountRef.current) {
      didMountRef.current = true;
      for (const step of steps) {
        const classified = classifyStep(step);
        if (!classified) continue;
        // Keep active agent steps alive across mode switch
        if (classified.type === 'agent' && isStepActive(classified.type, step)) continue;
        disposedIdsRef.current.add(classified.id);
      }
    }

    // Pass 1 — upsert from current steps
    for (const step of steps) {
      const classified = classifyStep(step);
      if (!classified) continue;
      const { type, id } = classified;
      seenIds.add(id);

      const existing = entries.get(id);
      const state = deriveState(type, step, isSpeaking);
      const body = bodyFor(type, step, state === 'running');
      const toolStatus =
        step.type === 'tool' ? (step.content as ToolContent).status : undefined;
      const status = statusFor(type, state, toolStatus);
      const title = titleFor(type, step);

      if (!existing) {
        // Don't open windows for steps that aren't actively producing output.
        // Those are history — either loaded with the conversation or completed
        // while we were in chat mode. Use isStepActive (not the derived state)
        // because deriveState can return 'running' for finished response steps
        // while TTS for a *different* turn is speaking.
        if (!isStepActive(type, step)) continue;
        // Don't reopen a window we already disposed — it represents a step
        // that already had its visible lifecycle (e.g. an interrupted response
        // that never received isFinal=true).
        if (disposedIdsRef.current.has(id)) continue;
        const slot = slotRef.current[type]++;
        const pos = cascadePosition(type, slot);
        const zIndex = ++zCounterRef.current;
        const descriptor: HudWindowDescriptor = {
          id,
          type,
          title,
          status,
          state,
          x: pos.x,
          y: pos.y,
          body,
          closing: false,
        };
        entries.set(id, {
          descriptor,
          lingerTimer: null,
          removeTimer: null,
          slot,
          hasStartedSpeaking: false,
        });
        setZOrder((prev) => ({ ...prev, [id]: zIndex }));
        continue;
      }

      // Cancel any pending close — but only if the step itself has actually
      // resumed producing output. Otherwise this would resurrect previous-turn
      // response windows every render (they live in `steps` forever).
      const stepActive = isStepActive(type, step);
      if (stepActive) {
        if (existing.lingerTimer !== null) {
          window.clearTimeout(existing.lingerTimer);
          existing.lingerTimer = null;
        }
        if (existing.removeTimer !== null) {
          window.clearTimeout(existing.removeTimer);
          existing.removeTimer = null;
        }
      }

      existing.descriptor = {
        ...existing.descriptor,
        title,
        status,
        state,
        body,
        closing: stepActive ? false : existing.descriptor.closing,
      };
    }

    // Latch hasStartedSpeaking on response windows the moment TTS starts.
    if (isSpeaking) {
      for (const entry of entries.values()) {
        if (entry.descriptor.type === 'response' && !entry.hasStartedSpeaking) {
          entry.hasStartedSpeaking = true;
        }
      }
    }

    // Pass 2 — schedule linger/close for windows whose step is finished
    for (const [id, entry] of entries) {
      if (!seenIds.has(id)) continue;
      const { descriptor } = entry;
      if (descriptor.closing) continue;
      if (entry.lingerTimer !== null) continue;

      // Response windows live exclusively on the audio gate. They stay open
      // forever until BOTH conditions hold:
      //   - hasStartedSpeaking === true (audio has played at least once)
      //   - isSpeaking === false       (audio is no longer playing — either
      //     finished naturally or stopped by the user via the stop button)
      // We never close a response window on text-final, on PROCESSING_ENDED,
      // or on any timeout. The user must hear the audio (or interrupt it).
      // Note: response windows BYPASS the `state === 'running'` check because
      // an interrupted step may never receive isFinal=true; the audio gate
      // is what tells us the window can close.
      if (descriptor.type === 'response') {
        if (isSpeaking) continue;
        if (!entry.hasStartedSpeaking) continue;
      } else {
        if (descriptor.state === 'running') continue;
      }

      const linger = LINGER_MS[descriptor.type];
      entry.lingerTimer = window.setTimeout(() => {
        const e = entries.get(id);
        if (!e) return;
        e.descriptor = { ...e.descriptor, closing: true };
        e.lingerTimer = null;
        bump();
        e.removeTimer = window.setTimeout(() => {
          entries.delete(id);
          disposedIdsRef.current.add(id);
          setZOrder((prev) => {
            if (!(id in prev)) return prev;
            const next = { ...prev };
            delete next[id];
            return next;
          });
          bump();
        }, CLOSE_ANIM_MS);
      }, linger);
    }

    // If user went idle entirely (no active session), trigger close on anything
    // still hanging around — EXCEPT response windows, which are governed
    // solely by the audio gate above. PROCESSING_ENDED commonly flips
    // isActive=false before the first audio chunk arrives; closing the
    // response window here would race the audio and cut it visually short.
    if (!isActive) {
      for (const [id, entry] of entries) {
        if (entry.descriptor.closing) continue;
        if (entry.lingerTimer !== null) continue;
        if (entry.descriptor.type === 'response') continue;
        entry.lingerTimer = window.setTimeout(() => {
          const e = entries.get(id);
          if (!e) return;
          e.descriptor = { ...e.descriptor, closing: true };
          e.lingerTimer = null;
          bump();
          e.removeTimer = window.setTimeout(() => {
            entries.delete(id);
            disposedIdsRef.current.add(id);
            setZOrder((prev) => {
              const next = { ...prev };
              delete next[id];
              return next;
            });
            bump();
          }, CLOSE_ANIM_MS);
        }, 600);
      }
    }

    bump();
    // Effect intentionally re-runs on steps / state changes — entries is a ref.
  }, [steps, isSpeaking, isActive]);

  // Reset cascade slots when no windows are open so positioning stays sane
  // across long sessions.
  useEffect(() => {
    if (entriesRef.current.size === 0) {
      slotRef.current = { thinking: 0, tool: 0, agent: 0, response: 0 };
    }
  }, [version]);

  // Cleanup all timers on unmount
  useEffect(() => {
    const entries = entriesRef.current;
    return () => {
      for (const entry of entries.values()) {
        if (entry.lingerTimer !== null) window.clearTimeout(entry.lingerTimer);
        if (entry.removeTimer !== null) window.clearTimeout(entry.removeTimer);
      }
    };
  }, []);

  const windows = useMemo<HudWindowDescriptor[]>(() => {
    const list: HudWindowDescriptor[] = [];
    for (const entry of entriesRef.current.values()) {
      list.push(entry.descriptor);
    }
    return list;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);

  const openCount = useMemo(
    () => windows.filter((w) => !w.closing).length,
    [windows],
  );

  const activeTone = useMemo<UseHudWindowsResult['activeTone']>(() => {
    // Prefer the most recent running window's type as the tone source
    let lastRunning: HudWindowDescriptor | null = null;
    for (const w of windows) {
      if (w.state === 'running' && !w.closing) {
        lastRunning = w;
      }
    }
    if (lastRunning) return lastRunning.type;
    return 'idle';
  }, [windows]);

  const brainStatusLabel = useMemo(() => {
    if (activeTone === 'thinking') return 'thinking';
    if (activeTone === 'tool') return 'tool · running';
    if (activeTone === 'agent') return 'subagent · running';
    if (activeTone === 'response') return 'speaking';
    return 'idle';
  }, [activeTone]);

  const raiseWindow = (id: string) => {
    const z = ++zCounterRef.current;
    setZOrder((prev) => ({ ...prev, [id]: z }));
  };

  return { windows, openCount, activeTone, brainStatusLabel, zOrder, raiseWindow };
}
