import { WeatherCard } from './WeatherCard';
import type { WeatherData } from './WeatherCard';
import { ApprovalCard } from './ApprovalCard';
import { ToolCard } from './ToolCard';
import { TextBubble } from './TextBubble';
import { ThinkingCard } from './ThinkingCard';
import type { Step, ToolContent, ApprovalContent } from '../../types/message';

interface MessageStepProps {
  step: Pick<Step, 'id' | 'type' | 'content'>;
  role: 'user' | 'assistant';
  onApprovalRespond?: (approvalId: string, approved: boolean) => void;
}

export const MessageStep = ({ step, role, onApprovalRespond }: MessageStepProps) => {
  if (step.type === 'text') {
    return <TextBubble content={step.content as string} role={role} />;
  }

  if (step.type === 'thinking') {
    return <ThinkingCard content={step.content as string} />;
  }

  if (step.type === 'tool') {
    return <ToolCard content={step.content as ToolContent} />;
  }

  if (step.type === 'weather') {
    return <WeatherCard data={step.content as WeatherData} />;
  }

  if (step.type === 'approval' && onApprovalRespond) {
    return <ApprovalCard content={step.content as ApprovalContent} onRespond={onApprovalRespond} />;
  }

  return null;
};
