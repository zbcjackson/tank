import { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Phone, PhoneOff, Ear, Square } from 'lucide-react';
import { WakeWordIndicator } from './WakeWordIndicator';
import { EnrollmentBanner } from './EnrollmentBanner';
import { VoiceApprovalOverlay } from './VoiceApprovalOverlay';
import { ListenModeSettings } from './ListenModeSettings';
import { PttButton } from './PttButton';
import { HudDesktop } from './Hud/HudDesktop';
import { useHudWindows } from './Hud/useHudWindows';
import type { OrbTone } from './Hud/HudOrb';
import type {
  AssistantStatus,
  ConversationState,
  ListenMode,
  Step,
} from '../../hooks/useAssistant';
import type { ApprovalContent } from '../../types/message';

interface VoiceModeProps {
  assistantStatus: AssistantStatus;
  isContinuousMicOn: boolean;
  onToggleContinuousMic: () => void;
  onStopSpeaking: () => void;
  statusText?: string;
  conversationState?: ConversationState;
  wakeWordKeyword?: string | null;
  speaker?: string;
  pauseAudioCapture: () => void;
  resumeAudioCapture: () => void;
  pendingApproval: ApprovalContent | null;
  onApprovalRespond: (approvalId: string, approved: boolean) => void;
  listenMode: ListenMode;
  voiceInterruptEnabled: boolean;
  wakeWordAvailable: boolean;
  onListenModeChange: (mode: ListenMode) => void;
  onVoiceInterruptEnabledChange: (enabled: boolean) => void;
  isPttActive: boolean;
  onPttStart: () => void;
  onPttStop: () => void;
  steps: Step[];
  sessionId: string;
  isSocketConnected: boolean;
  hasSocketError: boolean;
}

const statusVariants = {
  hidden: { opacity: 0, y: 6 },
  visible: { opacity: 1, y: 0 },
};

/** Map assistantStatus + context flags → visual orb tone. */
function deriveOrbTone(
  assistantStatus: AssistantStatus,
  conversationState: ConversationState | undefined,
  micOff: boolean,
  hasPendingApproval: boolean,
  hudActiveTone: 'idle' | 'thinking' | 'tool' | 'agent' | 'response',
): OrbTone {
  if (hasPendingApproval) return 'thinking';
  if (assistantStatus === 'error') return 'error';
  // Prefer the live HUD window tone — that's what's actually happening
  if (hudActiveTone !== 'idle') return hudActiveTone;
  if (assistantStatus === 'speaking') return 'response';
  if (assistantStatus === 'thinking' || assistantStatus === 'responding') return 'thinking';
  if (assistantStatus === 'tool_calling') return 'tool';
  if (conversationState === 'loading') return 'idle';
  if (micOff) return 'muted';
  return 'idle';
}

/** Map status into a Chinese label, same vocabulary as before. */
function deriveStatusLabel(
  assistantStatus: AssistantStatus,
  conversationState: ConversationState | undefined,
  listenMode: ListenMode,
  micOff: boolean,
  statusText?: string,
): string | undefined {
  switch (assistantStatus) {
    case 'speaking':
      return '回复中';
    case 'thinking':
    case 'responding':
      return '思考中';
    case 'tool_calling':
      return '工作中';
    case 'interrupted':
      return '已中断';
    case 'error':
      return '出错了';
    case 'idle':
      break;
  }
  if (conversationState === 'loading') return '正在加载唤醒词...';
  if (conversationState === 'idle') return undefined;
  if (listenMode === 'continuous' && micOff) return '点击按钮开始对话';
  if (listenMode === 'ptt') return '按住按钮说话';
  if (listenMode === 'wake_word') return undefined;
  return statusText || '等待语音输入';
}

export const VoiceMode = ({
  assistantStatus,
  isContinuousMicOn,
  onToggleContinuousMic,
  onStopSpeaking,
  statusText,
  conversationState,
  wakeWordKeyword,
  speaker,
  pauseAudioCapture,
  resumeAudioCapture,
  pendingApproval,
  onApprovalRespond,
  listenMode,
  voiceInterruptEnabled,
  wakeWordAvailable,
  onListenModeChange,
  onVoiceInterruptEnabledChange,
  isPttActive,
  onPttStart,
  onPttStop,
  steps,
  sessionId,
  isSocketConnected,
  hasSocketError,
}: VoiceModeProps) => {
  const [enrollmentKey, setEnrollmentKey] = useState(0);
  const isWakeWordIdle = conversationState === 'idle';
  const isWakeWordListening = conversationState === 'listening';
  const micOff = listenMode === 'continuous' && !isContinuousMicOn;

  const isSpeaking = assistantStatus === 'speaking';
  const isActive =
    assistantStatus !== 'idle' && assistantStatus !== 'interrupted' && assistantStatus !== 'error';

  const { windows, openCount, activeTone, brainStatusLabel, zOrder, raiseWindow } = useHudWindows({
    steps,
    isSpeaking,
    isActive,
  });

  const orbTone = deriveOrbTone(assistantStatus, conversationState, micOff, !!pendingApproval, activeTone);
  const statusLabel = deriveStatusLabel(assistantStatus, conversationState, listenMode, micOff, statusText);

  // Count distinct user-message turns for the bottom-right counter
  const turn = useMemo(() => {
    const seen = new Set<string>();
    for (const s of steps) {
      if (s.role === 'user' && s.msgId) seen.add(s.msgId);
    }
    return seen.size;
  }, [steps]);

  const voiceMeta =
    listenMode === 'continuous'
      ? isContinuousMicOn
        ? 'continuous · live'
        : 'continuous · muted'
      : listenMode === 'ptt'
      ? isPttActive
        ? 'ptt · holding'
        : 'ptt · ready'
      : isWakeWordListening
      ? 'wake · listening'
      : 'wake · idle';

  return (
    <motion.div
      key="voice"
      data-testid="voice-mode"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      className="h-full w-full relative overflow-hidden"
    >
      <HudDesktop
        windows={windows}
        zOrder={zOrder}
        onRaiseWindow={raiseWindow}
        orbTone={orbTone}
        ambientTone={activeTone}
        brainStatusLabel={brainStatusLabel}
        windowsOpen={openCount}
        turn={turn}
        sessionId={sessionId}
        speaker={speaker}
        socketConnected={isSocketConnected}
        socketError={hasSocketError}
        asrLabel="sherpa · zh+en"
        ttsLabel="edge · jenny"
        voiceMeta={voiceMeta}
      >
        {/* Status / wake-word / approval / controls live in this center column */}
        <div className="hud-status" data-tone={activeTone}>
          <AnimatePresence mode="wait">
            {isWakeWordIdle && !isActive ? (
              <WakeWordIndicator key="wake-word" keyword={wakeWordKeyword || 'Hey Tank'} />
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
                  className="hud-status__label"
                >
                  {statusLabel}
                </motion.p>
              )
            )}
          </AnimatePresence>
          <div className="hud-status__meta">
            {brainStatusLabel === 'idle' ? 'cognitive surface idle' : brainStatusLabel}
          </div>
        </div>

        <VoiceApprovalOverlay
          approval={pendingApproval}
          onRespond={onApprovalRespond}
        />

        <div className="relative flex items-center justify-center h-16 w-56">
          <div className="absolute left-0 top-1/2 -translate-y-1/2">
            <ListenModeSettings
              listenMode={listenMode}
              voiceInterruptEnabled={voiceInterruptEnabled}
              wakeWordAvailable={wakeWordAvailable}
              onListenModeChange={onListenModeChange}
              onVoiceInterruptEnabledChange={onVoiceInterruptEnabledChange}
            />
          </div>

          {listenMode === 'ptt' ? (
            <PttButton isRecording={isPttActive} onStart={onPttStart} onStop={onPttStop} size="lg" />
          ) : listenMode === 'wake_word' ? (
            <div
              data-testid="wake-word-indicator-button"
              data-state={isWakeWordListening ? 'listening' : 'idle'}
              className={`w-16 h-16 rounded-full flex items-center justify-center transition-all duration-300 ${
                isWakeWordListening
                  ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shadow-[0_0_30px_rgba(16,185,129,0.1)]'
                  : 'bg-zinc-800/40 text-zinc-500 border border-zinc-800/50'
              }`}
            >
              <Ear size={24} />
            </div>
          ) : (
            <motion.button
              whileHover={{ scale: 1.06 }}
              whileTap={{ scale: 0.94 }}
              onClick={onToggleContinuousMic}
              aria-label={isContinuousMicOn ? '挂断' : '开启麦克风'}
              aria-pressed={isContinuousMicOn}
              data-testid="continuous-mic-button"
              data-on={isContinuousMicOn ? 'true' : 'false'}
              className={`w-16 h-16 rounded-full flex items-center justify-center transition-all duration-300 ${
                isContinuousMicOn
                  ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shadow-[0_0_30px_rgba(16,185,129,0.1)]'
                  : 'bg-zinc-800/40 text-zinc-500 border border-zinc-800/50'
              }`}
            >
              {isContinuousMicOn ? <Phone size={24} /> : <PhoneOff size={24} />}
            </motion.button>
          )}

          <AnimatePresence>
            {isSpeaking && (
              <motion.button
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0, opacity: 0 }}
                whileHover={{ scale: 1.06 }}
                whileTap={{ scale: 0.94 }}
                onClick={onStopSpeaking}
                aria-label="停止播放"
                data-testid="voice-stop-button"
                className="absolute right-0 top-1/2 -translate-y-1/2 w-12 h-12 rounded-full flex items-center justify-center bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors"
              >
                <Square size={18} fill="currentColor" />
              </motion.button>
            )}
          </AnimatePresence>
        </div>
      </HudDesktop>

      {/* Enrollment banner — floating top, outside HudDesktop's center column */}
      <div className="absolute top-8 left-1/2 -translate-x-1/2 w-full max-w-md px-6 z-30">
        <EnrollmentBanner
          key={enrollmentKey}
          speaker={speaker}
          onEnrollComplete={() => setEnrollmentKey((k) => k + 1)}
          pauseAudioCapture={pauseAudioCapture}
          resumeAudioCapture={resumeAudioCapture}
        />
      </div>

    </motion.div>
  );
};
