import { useState, useMemo } from 'react';
import { Wrench, ChevronDown, ChevronUp } from 'lucide-react';
import clsx from 'clsx';
import type { ToolContent } from '../../types/message';

const PARAMS_COLLAPSED_ROWS = 3;
const RESULT_COLLAPSED_LINES = 6;

const STATUS_COLOR: Record<string, string> = {
  success: 'text-emerald-500/60',
  error: 'text-red-500/60',
};

function tryParseJson(str: string): unknown | null {
  try {
    return JSON.parse(str);
  } catch {
    return null;
  }
}

function formatArgValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
}

function ExpandToggle({
  expanded,
  onToggle,
}: {
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className="flex items-center gap-1 mt-1.5 text-[10px] font-mono text-text-muted hover:text-text-secondary transition-colors cursor-pointer"
    >
      {expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
      {expanded ? 'Show less' : 'Show more'}
    </button>
  );
}

function ToolParams({ args }: { args: string }) {
  const parsed = useMemo(() => tryParseJson(args), [args]);
  const [expanded, setExpanded] = useState(false);

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    if (!args || args === '{}') return null;
    return (
      <div className="text-[12px] font-mono bg-black/30 text-text-secondary/60 p-3 rounded-xl border border-border-subtle overflow-x-auto scrollbar-thin whitespace-pre">
        {args}
      </div>
    );
  }

  const entries = Object.entries(parsed as Record<string, unknown>);
  if (entries.length === 0) return null;

  const canCollapse = entries.length > PARAMS_COLLAPSED_ROWS;
  const visibleEntries = canCollapse && !expanded ? entries.slice(0, PARAMS_COLLAPSED_ROWS) : entries;

  return (
    <div>
      <div className="text-[12px] font-mono bg-black/30 p-3 rounded-xl border border-border-subtle space-y-1 overflow-x-auto scrollbar-thin">
        {visibleEntries.map(([key, value]) => (
          <div key={key} className="flex gap-3 whitespace-nowrap">
            <span className="text-text-muted shrink-0">{key}</span>
            <span className="text-text-secondary">{formatArgValue(value)}</span>
          </div>
        ))}
        {canCollapse && !expanded && (
          <div className="text-text-muted/50">
            ... {entries.length - PARAMS_COLLAPSED_ROWS} more
          </div>
        )}
      </div>
      {canCollapse && (
        <ExpandToggle expanded={expanded} onToggle={() => setExpanded((p) => !p)} />
      )}
    </div>
  );
}

function ToolResult({ result }: { result: string }) {
  const jsonParsed = useMemo(() => tryParseJson(result), [result]);
  const displayContent = jsonParsed !== null ? JSON.stringify(jsonParsed, null, 2) : result;

  const lines = displayContent.split('\n');
  const canCollapse = lines.length > RESULT_COLLAPSED_LINES;
  const [expanded, setExpanded] = useState(false);

  const visibleContent =
    canCollapse && !expanded
      ? lines.slice(0, RESULT_COLLAPSED_LINES).join('\n') + '\n…'
      : displayContent;

  return (
    <div>
      <div
        className={clsx(
          'text-[11px] font-mono bg-black/20 p-3 rounded-xl border border-border-subtle text-text-muted overflow-x-auto scrollbar-thin',
          expanded && canCollapse && 'max-h-96 overflow-y-auto',
        )}
      >
        <pre className="whitespace-pre m-0">
          <code>{visibleContent}</code>
        </pre>
      </div>
      {canCollapse && (
        <ExpandToggle expanded={expanded} onToggle={() => setExpanded((p) => !p)} />
      )}
    </div>
  );
}

export const ToolCard = ({ content }: { content: ToolContent }) => (
  <div className="w-full max-w-2xl">
    <div className="rounded-2xl rounded-tl-sm bg-surface-raised border border-border-subtle overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border-subtle">
        <Wrench size={12} className="text-amber-500/60" />
        <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase">
          {content.name}
        </span>
        <span
          className={clsx(
            'ml-auto text-[9px] font-mono tracking-wider uppercase',
            STATUS_COLOR[content.status] || 'text-amber-500/60',
          )}
        >
          {content.status}
        </span>
      </div>

      {/* Body */}
      <div className="p-3 space-y-2">
        <ToolParams args={content.arguments} />
        {content.result && <ToolResult result={content.result} />}
      </div>
    </div>
  </div>
);
