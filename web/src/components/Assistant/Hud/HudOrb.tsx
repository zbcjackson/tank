import { useMemo } from 'react';

export type OrbTone = 'idle' | 'thinking' | 'tool' | 'agent' | 'response' | 'error' | 'muted';

interface HudOrbProps {
  tone: OrbTone;
}

const TICK_COUNT = 60;

interface Tick {
  height: number;
  opacity: number;
  rotateDeg: number;
}

/**
 * Central HUD orb — concentric rings, rotating tick ring, glowing core.
 * The visible `tone` recolors the core via CSS data-tone attribute.
 */
export const HudOrb = ({ tone }: HudOrbProps) => {
  const ticks = useMemo<Tick[]>(() => {
    return Array.from({ length: TICK_COUNT }, (_, i) => ({
      height: i % 5 === 0 ? 9 : 4,
      opacity: i % 5 === 0 ? 0.45 : 0.18,
      rotateDeg: (i / TICK_COUNT) * 360,
    }));
  }, []);

  return (
    <div className="hud-orb" data-tone={tone}>
      <div className="hud-orb__halo" />
      <div className="hud-orb__ring hud-orb__ring--3" />
      <div className="hud-orb__ring hud-orb__ring--2" />
      <div className="hud-orb__ring hud-orb__ring--1" />
      <div className="hud-orb__ticks">
        {ticks.map((tick, i) => (
          <span
            key={i}
            className="hud-orb__tick"
            style={{
              height: `${tick.height}px`,
              opacity: tick.opacity,
              transform: `translateX(-50%) rotate(${tick.rotateDeg}deg)`,
            }}
          />
        ))}
      </div>
      <div className="hud-orb__core" />
    </div>
  );
};
