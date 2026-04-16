import { useState, useCallback, useMemo } from 'react';

import type { WebsocketMessage, Capabilities } from '../services/websocket';
import type { StatusEvent } from './useAssistantStatus';
import type { Step, StepType, ToolContent, ApprovalContent, Message } from '../types/message';
import type { WeatherData } from '../components/Assistant/WeatherCard';

/**
 * Parse weather tool result string into structured data.
 * Returns null if the content doesn't match the expected format.
 */
export function parseWeatherResult(content: string): WeatherData | null {
  try {
    const t = content.match(/'temperature':\s*'([^']+)'/);
    const c = content.match(/'condition':\s*'([^']+)'/);
    const l = content.match(/'location':\s*'([^']+)'/);
    if (t && c && l) {
      return { city: l[1], temp: t[1], condition: c[1], wind: '4km/h' };
    }
  } catch {
    // Malformed content — ignore
  }
  return null;
}

/**
 * Group flat steps into messages by msgId.
 */
function groupStepsByMsgId(steps: Step[]): Message[] {
  const map = new Map<string, Message>();
  for (const step of steps) {
    let msg = map.get(step.msgId);
    if (!msg) {
      msg = { id: step.msgId, role: step.role, steps: [], isComplete: false };
      map.set(step.msgId, msg);
    }
    msg.steps.push(step);
    if (step.isFinal) msg.isComplete = true;
  }
  return Array.from(map.values());
}

interface MessageReducerCallbacks {
  dispatchStatus: (event: StatusEvent) => void;
  onCapabilities: (caps: Capabilities) => void;
}

/**
 * Owns step/message state and the handleMessage logic for incoming WebSocket messages.
 *
 * Separated from useAssistant so the complex message-parsing/step-upsert logic
 * can be reasoned about (and tested) independently of audio and connection concerns.
 */
export function useMessageReducer(callbacks: MessageReducerCallbacks) {
  const [steps, setSteps] = useState<Step[]>([]);
  const [latestMessage, setLatestMessage] = useState<WebsocketMessage | null>(null);

  const clearSteps = useCallback(() => setSteps([]), []);

  const handleMessage = useCallback(
    (msg: WebsocketMessage) => {
      // Track latest message for conversation session hook
      setLatestMessage(msg);

      // --- Signal messages (capabilities, processing lifecycle) ---
      if (msg.type === 'signal') {
        if (msg.content === 'ready') {
          const caps = msg.metadata?.capabilities as Capabilities | undefined;
          if (caps) {
            callbacks.onCapabilities(caps);
          }
        } else if (msg.content === 'processing_started') {
          callbacks.dispatchStatus({ type: 'PROCESSING_STARTED' });
        } else if (msg.content === 'processing_ended') {
          callbacks.dispatchStatus({ type: 'PROCESSING_ENDED' });
        }
        return;
      }

      const role = msg.is_user ? 'user' : 'assistant';
      const msgId = msg.msg_id || (msg.is_user ? 'user_default' : 'assistant_default');

      // Parse activity type and turn
      const updateType = msg.metadata?.update_type;
      const metadataType = typeof updateType === 'string' ? updateType.split('.').pop() : null;
      const turn = msg.metadata?.turn || 0;

      let activityType: StepType = 'text';
      if (metadataType === 'THOUGHT') activityType = 'thinking';
      else if (metadataType === 'TOOL') activityType = 'tool';
      else if (metadataType === 'APPROVAL') activityType = 'approval';

      if (msg.type === 'transcript') activityType = 'text';

      const stepId = msg.metadata?.step_id as string;

      setSteps((prev) => {
        const updated = [...prev];
        const existingIdx = updated.findIndex((m) => m.id === stepId);

        // --- Reconcile backend echo with optimistic local user step ---
        if (msg.type === 'transcript' && msg.is_user) {
          const localIdx = updated.findLastIndex(
            (s) => s.role === 'user' && s.id.startsWith('local_') && s.content === msg.content,
          );
          if (localIdx > -1) {
            updated[localIdx] = {
              ...updated[localIdx],
              id: stepId,
              msgId,
              speaker: msg.speaker || updated[localIdx].speaker,
            };
            return updated;
          }
        }

        // --- TEXT & THINKING (Streaming) ---
        if (activityType === 'text' || activityType === 'thinking') {
          if (existingIdx > -1) {
            updated[existingIdx] = {
              ...updated[existingIdx],
              content:
                msg.type === 'transcript'
                  ? msg.content
                  : updated[existingIdx].content + (msg.content || ''),
              isFinal: msg.is_final,
              speaker: msg.speaker || updated[existingIdx].speaker,
            };
            return updated;
          } else {
            if (!msg.content && msg.is_final) return prev;

            return [
              ...prev,
              {
                id: stepId,
                role,
                type: activityType,
                content: msg.content || '',
                msgId,
                isFinal: msg.is_final,
                speaker: msg.speaker || undefined,
              },
            ];
          }
        }

        // --- TOOL ACTIVITIES ---
        if (activityType === 'tool') {
          const status = (msg.metadata?.status as string) || 'calling';
          const hasResult = status === 'success' || status === 'error';
          const toolData: ToolContent = {
            name: (msg.metadata?.name as string) || '',
            arguments: (msg.metadata?.arguments as string) || '',
            status,
            result: hasResult ? msg.content : undefined,
          };

          // Auto-resolve matching pending approval when tool starts executing
          if (status === 'executing' || status === 'success') {
            const approvalIdx = updated.findIndex(
              (s) =>
                s.type === 'approval' &&
                (s.content as ApprovalContent).toolName === toolData.name &&
                (s.content as ApprovalContent).status === 'pending',
            );
            if (approvalIdx > -1) {
              const ac = updated[approvalIdx].content as ApprovalContent;
              updated[approvalIdx] = {
                ...updated[approvalIdx],
                content: { ...ac, status: 'approved' },
              };
            }
          }

          if (existingIdx > -1) {
            const existing = updated[existingIdx].content as ToolContent;
            updated[existingIdx] = {
              ...updated[existingIdx],
              content: {
                ...existing,
                ...toolData,
                result: toolData.result || existing.result,
                status: toolData.status || existing.status,
              },
              isFinal: msg.is_final,
            };

            // Weather Card
            if (hasResult && (toolData.name === 'get_weather' || toolData.name === 'weather')) {
              const weatherId = `${msgId}_weather_${turn}_${msg.metadata?.index || 0}`;
              if (!updated.some((m) => m.id === weatherId)) {
                const weather = parseWeatherResult(msg.content);
                if (weather) {
                  updated.push({
                    id: weatherId,
                    role: 'assistant',
                    type: 'weather',
                    content: weather,
                    msgId,
                  });
                }
              }
            }
            return updated;
          } else {
            return [
              ...prev,
              {
                id: stepId,
                role,
                type: 'tool',
                content: toolData,
                msgId,
                isFinal: msg.is_final,
                speaker: msg.speaker || undefined,
              },
            ];
          }
        }

        // --- APPROVAL ACTIVITIES ---
        if (activityType === 'approval') {
          const approvalData: ApprovalContent = {
            approvalId: (msg.metadata?.approval_id as string) || '',
            toolName: (msg.metadata?.tool_name as string) || '',
            toolArgs: (msg.metadata?.tool_args as Record<string, unknown>) || {},
            description: (msg.metadata?.description as string) || msg.content || '',
            status: 'pending',
          };

          if (existingIdx > -1) {
            updated[existingIdx] = {
              ...updated[existingIdx],
              content: approvalData,
              isFinal: msg.is_final,
            };
            return updated;
          }

          return [
            ...prev,
            {
              id: stepId,
              role,
              type: 'approval' as const,
              content: approvalData,
              msgId,
              isFinal: msg.is_final,
            },
          ];
        }

        return prev;
      });

      // Dispatch status events for assistant messages (outside setSteps to avoid nesting)
      if (!msg.is_user && role === 'assistant') {
        if (activityType === 'text' && msg.type === 'text') {
          callbacks.dispatchStatus({ type: 'TEXT_DELTA' });
        } else if (activityType === 'tool') {
          const status = (msg.metadata?.status as string) || 'calling';
          if (status === 'calling' || status === 'executing') {
            callbacks.dispatchStatus({ type: 'TOOL_UPDATE' });
          } else if (status === 'success' || status === 'error') {
            callbacks.dispatchStatus({ type: 'TOOL_DONE' });
          }
        }
      }
    },
    [callbacks],
  );

  /**
   * Add an optimistic local user step (visible immediately before backend echo).
   */
  const addLocalUserStep = useCallback((text: string) => {
    const localMsgId = `local_${Date.now()}`;
    const localStepId = `${localMsgId}_text_0`;
    setSteps((prev) => [
      ...prev,
      {
        id: localStepId,
        role: 'user' as const,
        type: 'text' as const,
        content: text,
        msgId: localMsgId,
        isFinal: true,
      },
    ]);
  }, []);

  /**
   * Load history steps from a resumed session, replacing current steps.
   */
  const loadHistory = useCallback((historySteps: Step[]) => {
    setSteps(historySteps);
  }, []);

  const messages = useMemo(() => groupStepsByMsgId(steps), [steps]);

  return { steps, messages, latestMessage, handleMessage, clearSteps, addLocalUserStep, loadHistory };
}
