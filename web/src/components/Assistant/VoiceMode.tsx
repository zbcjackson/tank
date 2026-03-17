import { motion, AnimatePresence } from 'framer-motion';
import { Mic, MicOff, Square } from 'lucide-react';
import { Waveform } from './Waveform';
import { WakeWordIndicator } from './WakeWordIndicator';
import type { CalibrationState } from '../../services/audio';
import type { ConversationState } from '../../hooks/useAssistant';

interface VoiceModeProps {
  isAssistantTyping: boolean;
  isUserSpeaking: boolean;
  isMuted: boolean;
  isSpeaking: boolean;
  onMicClick: () => void;
  onStopSpeaking: () => void;
  statusText?: string;
  calibrationState: CalibrationState;
  getAnalyserNode?: () => AnalyserNode | null;
  conversationState?: ConversationState;
  ttsRms?: number;
}

const statusVariants = {
  hidden: { opacity: 0, y: 6 },
  visible: { opacity: 1, y: 0 },
};

const ORB_COLORS: Record<string, string> = {
  speaking: 'from-amber-500/40 via-orange-400/20 to-transparent',
  thinking: 'from-amber-600/25 via-amber-500/10 to-transparent',
  listening: 'from-emerald-500/30 via-emerald-400/10 to-transparent',
  muted: 'from-zinc-600/20 via-zinc-500/5 to-transparent',
  idle: 'from-amber-500/15 via-amber-400/5 to-transparent',
};

const ORB_ANIMATIONS: Record<string, object> = {
  speaking: {
    scale: [1, 1.1, 1],
    transition: { duration: 1.5, repeat: Infinity, ease: 'easeInOut' },
  },
  thinking: {
    scale: [1, 1.04, 1],
    opacity: [0.6, 0.9, 0.6],
    transition: { duration: 2.5, repeat: Infinity, ease: 'easeInOut' },
  },
  listening: {
    scale: [1, 1.06, 1],
    transition: { duration: 1, repeat: Infinity, ease: 'easeInOut' },
  },
  idle: { scale: 1, opacity: 0.6 },
  muted: { scale: 1, opacity: 0.6 },
};

const CORE_SPEAKING_ANIMATE = {
  scale: [1, 1.08, 1],
  transition: { duration: 1.2, repeat: Infinity, ease: 'easeInOut' },
};
const CORE_IDLE_ANIMATE = {};

const MIC_SPEAKING_ANIMATE = {
  scale: [1, 1.05, 1],
  transition: { repeat: Infinity, duration: 1.2 },
};
const MIC_IDLE_ANIMATE = {};

const RING_PULSE_ANIMATE = { scale: [1, 1.8], opacity: [0.4, 0] };
const RING_PULSE_TRANSITION = { duration: 2, repeat: Infinity, ease: 'easeOut' as const };

const VOICE_BG_STYLE = {
  background: 'radial-gradient(ellipse at 50% 40%, #141210 0%, #0a0a0a 70%)',
};
const ORB_CONTAINER_STYLE = { width: 280, height: 280 };
const ORB_GRADIENT_STYLE = { width: 200, height: 200 };

const AMBIENT_STYLES: Record<string, React.CSSProperties> = {
  speaking: {
    background: 'radial-gradient(circle at 50% 45%, rgba(212, 160, 84, 0.06) 0%, transparent 60%)',
  },
  thinking: {
    background: 'radial-gradient(circle at 50% 45%, rgba(212, 160, 84, 0.03) 0%, transparent 60%)',
  },
  none: { background: 'none' },
};

const coreStyle = (orbState: string): React.CSSProperties => ({
  width: 120,
  height: 120,
  background:
    orbState === 'muted'
      ? 'radial-gradient(circle, rgba(80,75,70,0.3) 0%, rgba(40,38,35,0.1) 70%)'
      : 'radial-gradient(circle, rgba(212,160,84,0.15) 0%, rgba(212,160,84,0.02) 70%)',
  boxShadow:
    orbState === 'speaking'
      ? '0 0 60px rgba(212,160,84,0.15), inset 0 0 30px rgba(212,160,84,0.05)'
      : 'inset 0 0 30px rgba(212,160,84,0.03)',
});

export const VoiceMode = ({
  isAssistantTyping,
  isUserSpeaking,
  isMuted,
  isSpeaking,
  onMicClick,
  onStopSpeaking,
  statusText,
  calibrationState,
  getAnalyserNode,
  conversationState,
  ttsRms,
}: VoiceModeProps) => {
  const isWakeWordIdle = conversationState === 'idle';
  const isWakeWordLoading = conversationState === 'loading';
  const isGateOpen = conversationState === 'active';
  const micStatus = isMuted ? 'muted' : isGateOpen ? 'active' : 'idle';

  const orbState = isSpeaking
    ? 'speaking'
    : isAssistantTyping
      ? 'thinking'
      : isWakeWordLoading
        ? 'idle'
        : isWakeWordIdle
          ? 'idle'
          : isUserSpeaking
            ? 'listening'
            : isMuted
              ? 'muted'
              : 'idle';

  const statusLabel = isSpeaking
    ? '回复中'
    : isAssistantTyping
      ? '思考中'
      : isWakeWordLoading
        ? '正在加载唤醒词...'
        : isWakeWordIdle
          ? undefined // WakeWordIndicator handles the status text
          : isMuted
            ? '已静音'
            : isUserSpeaking
              ? '聆听中'
              : statusText || '等待语音输入';

  const calibrationLabel =
    calibrationState.status === 'calibrating'
      ? '噪声校准中'
      : calibrationState.status === 'ready'
        ? '校准完成'
        : calibrationState.status === 'error'
          ? '使用默认阈值'
          : undefined;

  return (
    <motion.div
      key="voice"
      data-testid="voice-mode"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      className="grain h-full flex flex-col items-center justify-center relative overflow-hidden"
      style={VOICE_BG_STYLE}
    >
      {/* Ambient background glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={AMBIENT_STYLES[orbState] || AMBIENT_STYLES.none}
      />

      {/* Center content */}
      <div className="relative flex flex-col items-center gap-16 z-10">
        {/* Orb + Waveform */}
        <div className="relative flex items-center justify-center" style={ORB_CONTAINER_STYLE}>
          {/* Outer ring pulse (speaking only) */}
          {isSpeaking && (
            <motion.div
              className="absolute inset-0 rounded-full border border-amber-500/20"
              animate={RING_PULSE_ANIMATE}
              transition={RING_PULSE_TRANSITION}
            />
          )}

          {/* Orb gradient */}
          <motion.div
            className={`absolute rounded-full bg-gradient-radial ${ORB_COLORS[orbState]}`}
            style={ORB_GRADIENT_STYLE}
            animate={ORB_ANIMATIONS[orbState]}
          />

          {/* Inner core */}
          <motion.div
            className="absolute rounded-full"
            style={coreStyle(orbState)}
            animate={orbState === 'speaking' ? CORE_SPEAKING_ANIMATE : CORE_IDLE_ANIMATE}
          />

          {/* Waveform overlay (speaking) */}
          {isSpeaking && (
            <div className="absolute inset-0 flex items-center justify-center">
              <Waveform
                active={isSpeaking}
                getAnalyserNode={getAnalyserNode}
                rmsAmplitude={ttsRms}
              />
            </div>
          )}
        </div>

        {/* Status area */}
        <div className="flex flex-col items-center gap-3">
          <AnimatePresence mode="wait">
            {isWakeWordIdle && !isSpeaking && !isAssistantTyping ? (
              <WakeWordIndicator key="wake-word" keyword="Hey Tank" />
            ) : (
              statusLabel && (
                <motion.p
                  key={statusLabel}
                  data-testid="voice-status"
                  variants={statusVariants}
                  initial="hidden"
                  animate="visible"
                  exit="hidden"
                  transition={{ duration: 0.3 }}
                  className="text-sm font-medium tracking-wide text-text-secondary"
                >
                  {statusLabel}
                </motion.p>
              )
            )}
          </AnimatePresence>

          {calibrationLabel && (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className={`text-xs px-3 py-1 rounded-full border ${
                calibrationState.status === 'calibrating'
                  ? 'border-amber-800/50 text-amber-500/70 bg-amber-500/5'
                  : calibrationState.status === 'ready'
                    ? 'border-emerald-800/50 text-emerald-500/70 bg-emerald-500/5'
                    : 'border-rose-800/50 text-rose-500/70 bg-rose-500/5'
              }`}
            >
              {calibrationLabel}
            </motion.span>
          )}
        </div>

        {/* Controls — mic always centered, stop button to the right */}
        <div className="relative flex items-center justify-center h-16 w-48">
          <motion.button
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.94 }}
            animate={isUserSpeaking ? MIC_SPEAKING_ANIMATE : MIC_IDLE_ANIMATE}
            onClick={onMicClick}
            data-testid="mic-button"
            data-muted={isMuted ? 'true' : 'false'}
            className={`absolute left-1/2 -translate-x-1/2 w-16 h-16 rounded-full flex items-center justify-center transition-all duration-300 ${
              micStatus === 'muted'
                ? 'bg-zinc-800/80 text-zinc-500 border border-zinc-700/50'
                : micStatus === 'active'
                  ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shadow-[0_0_30px_rgba(16,185,129,0.1)]'
                  : 'bg-zinc-800/40 text-zinc-600 border border-zinc-800/50'
            }`}
          >
            {micStatus === 'muted' ? <MicOff size={24} /> : <Mic size={24} />}
          </motion.button>

          <AnimatePresence>
            {isSpeaking && (
              <motion.button
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0, opacity: 0 }}
                whileHover={{ scale: 1.06 }}
                whileTap={{ scale: 0.94 }}
                onClick={onStopSpeaking}
                data-testid="voice-stop-button"
                className="absolute right-0 top-1/2 -translate-y-1/2 w-12 h-12 rounded-full flex items-center justify-center bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors"
              >
                <Square size={18} fill="currentColor" />
              </motion.button>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Bottom brand mark */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2">
        <span className="text-[10px] font-mono tracking-[0.3em] text-text-muted/40 uppercase">
          Tank
        </span>
      </div>
    </motion.div>
  );
};
