import { useState } from 'react';
import type { HudWindowBody } from './types';

interface HudWindowBodyViewProps {
  body: HudWindowBody;
  /** True while the window is in 'running' state (drives blinking cursor). */
  streamingState: boolean;
}

const WAVEFORM_BAR_COUNT = 40;

const Cursor = () => <span className="hud-cursor" aria-hidden="true" />;

const SectionLabel = ({ children }: { children: string }) => (
  <div className="hud-section-label">{children}</div>
);

interface KvBlockProps {
  pairs: Array<[string, string]>;
}
const KvBlock = ({ pairs }: KvBlockProps) => (
  <div className="hud-kv-block">
    {pairs.map(([k, v], i) => (
      <span key={i} style={{ display: 'contents' }}>
        <span className="hud-kv-block__k">{k}</span>
        <span className="hud-kv-block__v">{v}</span>
      </span>
    ))}
  </div>
);

const Waveform = () => {
  const [bars] = useState(() =>
    Array.from({ length: WAVEFORM_BAR_COUNT }, (_, i) => ({
      delay: `${i * 30}ms`,
      height: `${Math.random() * 80 + 20}%`,
    })),
  );
  return (
    <div className="hud-response-waveform" aria-hidden="true">
      {bars.map((b, i) => (
        <span
          key={i}
          className="hud-response-waveform__bar"
          style={{ animationDelay: b.delay, height: b.height }}
        />
      ))}
    </div>
  );
};

/** Renders the body content for a given window descriptor. */
export const HudWindowBodyView = ({ body, streamingState }: HudWindowBodyViewProps) => {
  if (body.kind === 'thinking') {
    return (
      <>
        <span className="hud-stream-text hud-stream-text--italic">{body.text}</span>
        {body.streaming && streamingState && <Cursor />}
      </>
    );
  }

  if (body.kind === 'tool') {
    return (
      <>
        <SectionLabel>input</SectionLabel>
        {body.args.length > 0 ? (
          <KvBlock pairs={body.args} />
        ) : (
          <div className="hud-kv-block">
            <span className="hud-kv-block__k">tool</span>
            <span className="hud-kv-block__v">{body.toolName}</span>
          </div>
        )}
        {body.output !== null && (
          <>
            <SectionLabel>output</SectionLabel>
            <div className="hud-code-block">
              {body.output}
              {body.streaming && streamingState && <Cursor />}
            </div>
          </>
        )}
        {body.output === null && body.streaming && streamingState && (
          <div style={{ marginTop: 4 }}>
            <span className="hud-stream-text hud-stream-text--italic">awaiting result</span>
            <Cursor />
          </div>
        )}
      </>
    );
  }

  if (body.kind === 'agent') {
    return (
      <>
        <SectionLabel>task</SectionLabel>
        <div
          className="hud-stream-text"
          style={{ color: 'var(--hud-text-dim)', marginBottom: 14 }}
        >
          {body.task || `delegated to ${body.subagentType || 'subagent'}`}
        </div>

        {body.activities.length > 0 && (
          <>
            <SectionLabel>activity</SectionLabel>
            <div className="hud-activity-list">
              {body.activities.map((a, i) => (
                <div key={i} className="hud-activity-list__item">
                  <span className="hud-activity-list__bullet">◦</span>
                  <span className="hud-activity-list__name">{a.name}</span>
                  <span
                    className={
                      a.done
                        ? 'hud-activity-list__check'
                        : 'hud-activity-list__check hud-activity-list__check--running'
                    }
                  >
                    {a.done ? '✓' : '⟳'}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}

        {body.summary && (
          <>
            <SectionLabel>summary</SectionLabel>
            <div className="hud-stream-text" style={{ color: 'var(--hud-text-dim)' }}>
              {body.summary}
              {body.summaryStreaming && streamingState && <Cursor />}
            </div>
          </>
        )}
      </>
    );
  }

  // response
  return (
    <>
      {body.streaming && streamingState && <Waveform />}
      <div className="hud-stream-text">
        {body.text}
        {body.streaming && streamingState && <Cursor />}
      </div>
    </>
  );
};
