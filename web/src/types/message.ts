import type { WeatherData } from '../components/Assistant/WeatherCard';

export type StepType = 'thinking' | 'tool' | 'text' | 'weather' | 'approval';

export interface ToolContent {
  name: string;
  arguments: string;
  status: string;
  result?: string;
}

export interface ApprovalContent {
  approvalId: string;
  toolName: string;
  toolArgs: Record<string, unknown>;
  description: string;
  status: 'pending' | 'approved' | 'rejected' | 'expired';
}

export interface Step {
  id: string;
  role: 'user' | 'assistant';
  type: StepType;
  content: string | ToolContent | WeatherData | ApprovalContent;
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
