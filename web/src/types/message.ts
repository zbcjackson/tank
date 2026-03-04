import type { WeatherData } from '../components/Assistant/WeatherCard';

export type StepType = 'thinking' | 'tool' | 'text' | 'weather';

export interface ToolContent {
  name: string;
  arguments: string;
  status: string;
  result?: string;
}

export interface Step {
  id: string;
  role: 'user' | 'assistant';
  type: StepType;
  content: string | ToolContent | WeatherData;
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
