import { motion } from 'framer-motion';
import { Wrench } from 'lucide-react';
import { WeatherCard } from './WeatherCard';
import type { WeatherData } from './WeatherCard';
import { ApprovalCard } from './ApprovalCard';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Step, ToolContent, ApprovalContent } from '../../types/message';

const remarkPlugins = [remarkGfm];

const markdownComponents = {
  p: (props: React.ComponentProps<'p'>) => <p className="mb-2 last:mb-0" {...props} />,
  ul: (props: React.ComponentProps<'ul'>) => (
    <ul className="list-disc ml-4 mb-2 text-text-secondary" {...props} />
  ),
  ol: (props: React.ComponentProps<'ol'>) => (
    <ol className="list-decimal ml-4 mb-2 text-text-secondary" {...props} />
  ),
  strong: (props: React.ComponentProps<'strong'>) => (
    <strong className="font-semibold text-text-primary" {...props} />
  ),
  a: (props: React.ComponentProps<'a'>) => (
    <a className="text-amber-400 underline underline-offset-2 hover:text-amber-300" {...props} />
  ),
  code: (props: React.ComponentProps<'code'>) => (
    <code
      className="bg-white/5 px-1.5 py-0.5 rounded text-[13px] font-mono text-amber-300/80"
      {...props}
    />
  ),
  pre: (props: React.ComponentProps<'pre'>) => (
    <pre
      className="bg-black/40 border border-border-subtle p-3 rounded-xl overflow-x-auto my-2 font-mono text-[13px] text-text-secondary"
      {...props}
    />
  ),
};

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
    const content = step.content as ToolContent;
    return (
      <div className="w-full max-w-2xl">
        <div className="rounded-2xl rounded-tl-sm bg-surface-raised border border-border-subtle overflow-hidden">
          {/* Tool header */}
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border-subtle">
            <Wrench size={12} className="text-amber-500/60" />
            <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase">
              {content.name}
            </span>
            <span
              className={`ml-auto text-[9px] font-mono tracking-wider uppercase ${
                content.status === 'success'
                  ? 'text-emerald-500/60'
                  : content.status === 'error'
                    ? 'text-red-500/60'
                    : 'text-amber-500/60'
              }`}
            >
              {content.status}
            </span>
          </div>

          {/* Tool body */}
          <div className="p-3 space-y-2">
            <div className="text-[12px] font-mono bg-black/30 text-text-secondary p-3 rounded-xl border border-border-subtle">
              <span className="text-text-muted mr-2">$</span>
              <span className="text-amber-400/80">{content.name}</span>
              <span className="text-text-muted"> </span>
              <span className="text-text-secondary/60">{JSON.stringify(content.arguments)}</span>
            </div>
            {content.result && (
              <div className="text-[11px] font-mono bg-black/20 p-3 rounded-xl border border-border-subtle text-text-muted max-h-48 overflow-y-auto scrollbar-thin">
                {content.result}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (step.type === 'weather') {
    return <WeatherCard data={step.content as WeatherData} />;
  }

  if (step.type === 'approval' && onApprovalRespond) {
    return <ApprovalCard content={step.content as ApprovalContent} onRespond={onApprovalRespond} />;
  }

  return null;
};
