export type HudTone = 'idle' | 'thinking' | 'tool' | 'agent' | 'response' | 'error' | 'muted';

export type HudWindowType = 'thinking' | 'tool' | 'agent' | 'response';

export type HudWindowState = 'running' | 'done' | 'error';

/**
 * Descriptor for a single floating HUD window. Produced by
 * {@link useHudWindows} from the live Step stream and the lifecycle
 * machine that wraps each Step. Pure data — the consumer renders it.
 */
export interface HudWindowDescriptor {
  /** Stable id mirroring the originating step id when possible. */
  id: string;
  type: HudWindowType;
  /** Header title (without the leading ◉ accent — that's added by the view). */
  title: string;
  /** Short status text shown in the header right-side. */
  status: string;
  /** Lifecycle state, controls dot/footer/status styling. */
  state: HudWindowState;
  /** Initial top-left position in pixels. */
  x: number;
  y: number;
  /** Body content payload — interpreted per `type`. */
  body: HudWindowBody;
  /** When true, the view should apply the closing animation. */
  closing: boolean;
}

export type HudWindowBody =
  | { kind: 'thinking'; text: string; streaming: boolean }
  | {
      kind: 'tool';
      toolName: string;
      args: Array<[string, string]>;
      output: string | null;
      streaming: boolean;
    }
  | {
      kind: 'agent';
      subagentType: string;
      task: string;
      activities: Array<{ name: string; done: boolean; detail?: string }>;
      summary: string;
      summaryStreaming: boolean;
    }
  | { kind: 'response'; text: string; streaming: boolean };
