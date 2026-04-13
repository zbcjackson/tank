import { motion } from 'framer-motion';
import { WeatherCard } from './WeatherCard';
import type { WeatherData } from './WeatherCard';
import { ApprovalCard } from './ApprovalCard';
import { ToolCard } from './ToolCard';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Step, ToolContent, ApprovalContent } from '../../types/message';
import { remarkPlugins, markdownComponents } from './markdownConfig';

interface MessageStepProps {
  step: Pick<Step, 'id' | 'type' | 'content'>;
  role: 'user' | 'assistant';
  onApprovalRespond?: (approvalId: string, approved: boolean) => void;
}

export const MessageStep = ({ step, role, onApprovalRespond }: MessageStepProps) => {
  if (step.type === 'text') {
    return (
      <div
        className={`px-4 py-3 rounded-2xl text-[14px] leading-relaxed ${
          role === 'user'
            ? 'bg-amber-500/10 text-text-primary border border-amber-500/10 rounded-tr-sm'
            : 'bg-surface-raised text-text-primary border border-border-subtle rounded-tl-sm'
        }`}
      >
        <ReactMarkdown remarkPlugins={remarkPlugins} components={markdownComponents}>
          {step.content as string}
        </ReactMarkdown>
      </div>
    );
  }

  if (step.type === 'thinking') {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="w-full max-w-2xl">
        <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-surface/50 border border-border-subtle text-[13px] text-text-muted leading-relaxed">
          <div className="flex items-center gap-2 mb-1.5">
            <motion.div
              className="w-1 h-1 rounded-full bg-amber-500/50"
              animate={{ opacity: [0.3, 1, 0.3] }}
              transition={{ repeat: Infinity, duration: 2 }}
            />
            <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase">
              Thinking
            </span>
          </div>
          <div className="text-text-secondary/70 italic">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{step.content as string}</ReactMarkdown>
          </div>
        </div>
      </motion.div>
    );
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
