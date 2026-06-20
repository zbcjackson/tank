import { useMemo } from 'react';
import type { Step, ToolContent } from '../types/message';

export interface BackgroundTask {
  stepId: string;
  agentType: string;
  description: string;
  activities: Array<{ name: string; done: boolean }>;
}

function isBackgroundWorker(step: Step): boolean {
  if (step.type !== 'tool' || step.role !== 'assistant') return false;
  const tc = step.content as ToolContent;
  if (tc.name !== 'agent') return false;
  try {
    const args: unknown = JSON.parse(tc.arguments || '{}');
    if (args && typeof args === 'object' && 'background' in args) {
      return (args as Record<string, unknown>).background === true;
    }
  } catch {
    // partial JSON during streaming
  }
  return false;
}

function isTerminal(status: string): boolean {
  return status === 'success' || status === 'error';
}

function deriveAgentType(tc: ToolContent): string {
  try {
    const args: unknown = JSON.parse(tc.arguments || '{}');
    if (args && typeof args === 'object') {
      const obj = args as Record<string, unknown>;
      if (typeof obj.subagent_type === 'string' && obj.subagent_type) {
        return obj.subagent_type;
      }
    }
  } catch {
    // ignore
  }
  return 'subagent';
}

function deriveDescription(tc: ToolContent): string {
  try {
    const args: unknown = JSON.parse(tc.arguments || '{}');
    if (args && typeof args === 'object') {
      const obj = args as Record<string, unknown>;
      if (typeof obj.description === 'string' && obj.description) {
        return obj.description;
      }
    }
  } catch {
    // ignore
  }
  return '';
}

export function useActiveBackgroundTasks(steps: Step[]): BackgroundTask[] {
  return useMemo(() => {
    return steps
      .filter(isBackgroundWorker)
      .filter((s) => !isTerminal((s.content as ToolContent).status))
      .map((s) => {
        const tc = s.content as ToolContent;
        return {
          stepId: s.id,
          agentType: deriveAgentType(tc),
          description: deriveDescription(tc),
          activities: tc.activities ?? [],
        };
      });
  }, [steps]);
}
