import { useCallback, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import type { HudWindowDescriptor } from './types';
import { HudWindowBodyView } from './HudWindowBody';

interface HudWindowProps {
  descriptor: HudWindowDescriptor;
  zIndex: number;
  onFocus: () => void;
}

interface DragState {
  pointerId: number;
  startX: number;
  startY: number;
  baseX: number;
  baseY: number;
}

export const HudWindow = ({ descriptor, zIndex, onFocus }: HudWindowProps) => {
  const [pos, setPos] = useState({ x: descriptor.x, y: descriptor.y });
  const dragRef = useRef<DragState | null>(null);

  const handleHeaderPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (descriptor.closing) return;
      const target = e.target;
      if (target instanceof HTMLElement && target.closest('button')) return;
      dragRef.current = {
        pointerId: e.pointerId,
        startX: e.clientX,
        startY: e.clientY,
        baseX: pos.x,
        baseY: pos.y,
      };
      e.currentTarget.setPointerCapture(e.pointerId);
      onFocus();
    },
    [descriptor.closing, onFocus, pos.x, pos.y],
  );

  const handleHeaderPointerMove = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    const dx = e.clientX - drag.startX;
    const dy = e.clientY - drag.startY;
    setPos({ x: drag.baseX + dx, y: drag.baseY + dy });
  }, []);

  const endDrag = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    dragRef.current = null;
  }, []);

  const className = [
    'hud-window',
    `hud-window--${descriptor.type}`,
    descriptor.closing ? 'hud-window--closing' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div
      className={className}
      data-state={descriptor.state}
      data-window-type={descriptor.type}
      style={{ left: pos.x, top: pos.y, zIndex }}
      onPointerDown={onFocus}
    >
      <div className="hud-window__sweep" />
      <div
        className="hud-window__header"
        onPointerDown={handleHeaderPointerDown}
        onPointerMove={handleHeaderPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <div className="hud-window__dot" />
        <div className="hud-window__title">
          <span className="hud-window__title-accent">◉</span>
          <span>{descriptor.title}</span>
        </div>
        <div className="hud-window__status">{descriptor.status}</div>
        <div className="hud-window__chips">
          <div className="hud-window__chip" />
          <div className="hud-window__chip" />
          <div className="hud-window__chip" />
        </div>
      </div>
      <div className="hud-window__body">
        <HudWindowBodyView
          body={descriptor.body}
          streamingState={descriptor.state === 'running'}
        />
      </div>
      <div className="hud-window__footer" />
    </div>
  );
};
