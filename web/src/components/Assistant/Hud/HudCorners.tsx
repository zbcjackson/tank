interface HudCornersProps {
  brainStatusLabel: string;
  sessionId: string;
  speaker?: string;
  socketConnected: boolean;
  socketError: boolean;
  windowsOpen: number;
  turn: number;
  asrLabel: string;
  ttsLabel: string;
  voiceMeta?: string;
}

/**
 * Four corner overlays — brand top-left, link/session top-right, signal
 * chain readouts bottom-left, counters bottom-right. Pure presentation,
 * driven entirely by props.
 */
export const HudCorners = ({
  brainStatusLabel,
  sessionId,
  speaker,
  socketConnected,
  socketError,
  windowsOpen,
  turn,
  asrLabel,
  ttsLabel,
  voiceMeta,
}: HudCornersProps) => {
  const indicatorClass = socketError
    ? 'hud-chrome__indicator hud-chrome__indicator--error'
    : socketConnected
    ? 'hud-chrome__indicator'
    : 'hud-chrome__indicator hud-chrome__indicator--idle';

  const indicatorLabel = socketError
    ? 'SOCKET · ERROR'
    : socketConnected
    ? 'SOCKET · LIVE'
    : 'SOCKET · WAIT';

  return (
    <>
      <div className="hud-chrome hud-chrome--tl">
        <div className="hud-chrome__bracket" />
        <div className="hud-chrome__group">
          <div className="hud-chrome__title">Tank</div>
          <div className="hud-chrome__sub">cognitive surface</div>
        </div>
      </div>

      <div className="hud-chrome hud-chrome--tr">
        <div className="hud-chrome__bracket" />
        <div className="hud-chrome__group">
          <div className={indicatorClass}>{indicatorLabel}</div>
          <div className="hud-chrome__readout hud-chrome__readout--right">
            <span>SESSION</span>
            <span>{sessionId}</span>
            {speaker && (
              <>
                <span>SPEAKER</span>
                <span>{speaker}</span>
              </>
            )}
            {voiceMeta && (
              <>
                <span>VOICE</span>
                <span>{voiceMeta}</span>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="hud-chrome hud-chrome--bl">
        <div className="hud-chrome__bracket" />
        <div className="hud-chrome__group">
          <div className="hud-chrome__readout">
            <span>ASR</span>
            <span>{asrLabel}</span>
            <span>TTS</span>
            <span>{ttsLabel}</span>
            <span>BRAIN</span>
            <span>{brainStatusLabel}</span>
          </div>
        </div>
      </div>

      <div className="hud-chrome hud-chrome--br">
        <div className="hud-chrome__bracket" />
        <div className="hud-chrome__group">
          <div className="hud-chrome__readout hud-chrome__readout--right">
            <span>WIN OPEN</span>
            <span>{windowsOpen}</span>
            <span>TURN</span>
            <span>{turn}</span>
          </div>
        </div>
      </div>
    </>
  );
};
