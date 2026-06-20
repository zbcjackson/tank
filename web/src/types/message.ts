import type { WeatherData } from '../components/Assistant/WeatherCard';

export type StepType = 'thinking' | 'tool' | 'text' | 'weather' | 'approval' | 'image';

export interface ToolContent {
  name: string;
  arguments: string;
  status: string;
  result?: string;
  activities?: Array<{ name: string; done: boolean }>;
}

export interface ApprovalContent {
  approvalId: string;
  toolName: string;
  toolArgs: Record<string, unknown>;
  description: string;
  status: 'pending' | 'approved' | 'rejected' | 'expired';
}

/**
 * Phase 17: assistant-sent image. Lives as its own Step kind so the
 * reducer's optimistic merge / msg-id grouping treats it like any
 * other turn segment. ``url`` is always something the browser can
 * fetch directly — backend rewrites ``media://`` URIs to ``/api/media/``
 * before the WebSocket frame leaves the server.
 */
export interface ImageContent {
  url: string;
  mimeType: string;
  caption: string;
}

export interface Step {
  id: string;
  role: 'user' | 'assistant';
  type: StepType;
  content: string | ToolContent | WeatherData | ApprovalContent | ImageContent;
  msgId: string;
  isFinal?: boolean;
  speaker?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  steps: Step[];
  isComplete: boolean;
}
