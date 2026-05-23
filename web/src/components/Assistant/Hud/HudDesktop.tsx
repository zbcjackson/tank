import './hud.css';

import { Starfield } from './Starfield';
import { HudParticles } from './HudParticles';
import { HudCorners } from './HudCorners';
import { HudOrb, type OrbTone } from './HudOrb';
import { HudWindow } from './HudWindow';
import type { HudWindowDescriptor } from './types';

interface HudDesktopProps {
  windows: HudWindowDescriptor[];
  zOrder: Record<string, number>;
  onRaiseWindow: (id: string) => void;
  orbTone: OrbTone;
  ambientTone: 'idle' | 'thinking' | 'tool' | 'agent' | 'response';
  brainStatusLabel: string;
  windowsOpen: number;
  turn: number;
  sessionId: string;
  speaker?: string;
  socketConnected: boolean;
  socketError: boolean;
  asrLabel: string;
  ttsLabel: string;
  voiceMeta?: string;
  /** Children render inside the HUD, above the background but in flow. */
  children?: React.ReactNode;
}

/**
 * Composite background layer for Voice mode. Holds:
 *  - All ambient/background visuals
 *  - The four corner readouts
 *  - The central orb (replaces the old radial-gradient orb)
 *  - The floating windows layer
 *
 * Children (status text, controls, approval overlay, etc.) render on top
 * of this layer in normal flow.
 */
export const HudDesktop = ({
  windows,
  zOrder,
  onRaiseWindow,
  orbTone,
  ambientTone,
  brainStatusLabel,
  windowsOpen,
  turn,
  sessionId,
  speaker,
  socketConnected,
  socketError,
  asrLabel,
  ttsLabel,
  voiceMeta,
  children,
}: HudDesktopProps) => {
  return (
    <div className="hud-root absolute inset-0 overflow-hidden">
      <div className="hud-bg" aria-hidden="true" />
      <Starfield />
      <HudParticles />
      <div className="hud-grid" aria-hidden="true" />
      <div className="hud-scan" aria-hidden="true" />
      <div className="hud-ambient" data-tone={ambientTone} aria-hidden="true" />
      <div className="hud-vignette" aria-hidden="true" />

      <HudCorners
        brainStatusLabel={brainStatusLabel}
        sessionId={sessionId}
        speaker={speaker}
        socketConnected={socketConnected}
        socketError={socketError}
        windowsOpen={windowsOpen}
        turn={turn}
        asrLabel={asrLabel}
        ttsLabel={ttsLabel}
        voiceMeta={voiceMeta}
      />

      {/* Center column — orb + status + controls (children) */}
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none z-10">
        <div className="flex flex-col items-center gap-9 pointer-events-auto">
          <HudOrb tone={orbTone} />
          {children}
        </div>
      </div>

      {/* Windows layer — floats above everything except corner chrome */}
      <div className="hud-windows">
        {windows.map((descriptor) => (
          <HudWindow
            key={descriptor.id}
            descriptor={descriptor}
            zIndex={zOrder[descriptor.id] ?? 100}
            onFocus={() => onRaiseWindow(descriptor.id)}
          />
        ))}
      </div>
    </div>
  );
};
