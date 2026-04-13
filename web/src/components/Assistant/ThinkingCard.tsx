import { motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import { remarkPlugins } from './markdownConfig';

interface ThinkingCardProps {
  content: string;
}

export const ThinkingCard = ({ content }: ThinkingCardProps) => (
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
        <ReactMarkdown remarkPlugins={remarkPlugins}>{content}</ReactMarkdown>
      </div>
    </div>
  </motion.div>
);
