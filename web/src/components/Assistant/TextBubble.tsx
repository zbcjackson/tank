import ReactMarkdown from 'react-markdown';
import { remarkPlugins, markdownComponents } from './markdownConfig';

interface TextBubbleProps {
  content: string;
  role: 'user' | 'assistant';
}

export const TextBubble = ({ content, role }: TextBubbleProps) => (
  <div
    className={`px-4 py-3 rounded-2xl text-[14px] leading-relaxed ${
      role === 'user'
        ? 'bg-amber-500/10 text-text-primary border border-amber-500/10 rounded-tr-sm'
        : 'bg-surface-raised text-text-primary border border-border-subtle rounded-tl-sm'
    }`}
  >
    <ReactMarkdown remarkPlugins={remarkPlugins} components={markdownComponents}>
      {content}
    </ReactMarkdown>
  </div>
);
