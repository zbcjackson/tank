import { useReducer, useCallback, useEffect, useRef } from 'react';

/**
 * Assistant activity states — what the assistant is currently doing.
 * Separate from connection state (idle/connecting/connected/reconnecting/failed).
 */
export type AssistantStatus =
  | 'idle'
  | 'thinking'
  | 'tool_calling'
  | 'speaking'
  | 'responding'
  | 'interrupted'
  | 'error';

/**
 * Events that drive state transitions.
 */
export type StatusEvent =
  | { type: 'PROCESSING_STARTED' }
  | { type: 'PROCESSING_ENDED' }
  | { type: 'TEXT_DELTA' }
  | { type: 'AUDIO_CHUNK' }
  | { type: 'TOOL_UPDATE' }
  | { type: 'TOOL_DONE' }
  | { type: 'SPEAKING_ENDED' }
  | { type: 'INTERRUPT' }
  | { type: 'ERROR' }
  | { type: 'RESET' };

/** States that count as "active processing" — can be interrupted or error'd */
const ACTIVE_STATES: ReadonlySet<AssistantStatus> = new Set([
  'thinking',
  'tool_calling',
  'speaking',
  'responding',
]);

/**
 * Pure state machine reducer. Given current status + event → next status.
 * Returns the same status reference if no transition applies (no-op).
 */
export function statusReducer(state: AssistantStatus, event: StatusEvent): AssistantStatus {
  switch (event.type) {
    case 'PROCESSING_STARTED':
      // Backend started processing — enter thinking from idle
      if (state === 'idle') return 'thinking';
      return state;

    case 'TOOL_UPDATE':
      // LLM requested a tool call
      if (state === 'thinking') return 'tool_calling';
      return state;

    case 'TOOL_DONE':
      // Tool finished — back to thinking so LLM can continue
      if (state === 'tool_calling') return 'thinking';
      return state;

    case 'TEXT_DELTA':
      // First text delta → responding (chat mode output)
      if (state === 'thinking') return 'responding';
      // Already responding or speaking — stay
      return state;

    case 'AUDIO_CHUNK':
      // First audio chunk → speaking (voice mode output)
      // Can arrive from thinking, responding, or even idle (audio lags behind processing_ended)
      if (state === 'thinking' || state === 'responding' || state === 'idle') return 'speaking';
      // Already speaking — stay
      return state;

    case 'SPEAKING_ENDED':
      // Audio buffer drained — go idle
      if (state === 'speaking') return 'idle';
      return state;

    case 'PROCESSING_ENDED':
      // Backend done. If speaking, stay — audio buffer still draining.
      if (state === 'speaking') return state;
      // For interrupted/error, this confirms cleanup — go idle
      if (state === 'interrupted' || state === 'error') return 'idle';
      // For all other active states (including responding), go idle.
      // If audio arrives after this, AUDIO_CHUNK from idle → speaking handles it.
      if (ACTIVE_STATES.has(state)) return 'idle';
      return state;

    case 'INTERRUPT':
      // Can interrupt any active state
      if (ACTIVE_STATES.has(state)) return 'interrupted';
      return state;

    case 'ERROR':
      // Error during any active state
      if (ACTIVE_STATES.has(state)) return 'error';
      return state;

    case 'RESET':
      return 'idle';

    default:
      return state;
  }
}

/** Safety timeout durations for transient states */
const INTERRUPTED_TIMEOUT_MS = 3000;
const ERROR_TIMEOUT_MS = 5000;

/**
 * React hook wrapping the status state machine.
 * Provides dispatch + auto-recovery timeouts for transient states.
 */
export function useAssistantStatus() {
  const [status, dispatch] = useReducer(statusReducer, 'idle');
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-recover from transient states (interrupted, error)
  useEffect(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }

    if (status === 'interrupted') {
      timeoutRef.current = setTimeout(() => {
        dispatch({ type: 'RESET' });
      }, INTERRUPTED_TIMEOUT_MS);
    } else if (status === 'error') {
      timeoutRef.current = setTimeout(() => {
        dispatch({ type: 'RESET' });
      }, ERROR_TIMEOUT_MS);
    }

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [status]);

  const dispatchStatus = useCallback((event: StatusEvent) => {
    dispatch(event);
  }, []);

  return { assistantStatus: status, dispatchStatus };
}
