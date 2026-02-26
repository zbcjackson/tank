import { motion } from 'framer-motion';
import { Mic, MicOff, Square } from 'lucide-react';
import { Waveform } from './Waveform';
import type { CalibrationState } from '../../services/audio';

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
}

export const VoiceMode = ({ isAssistantTyping, isUserSpeaking, isMuted, isSpeaking, onMicClick, onStopSpeaking, statusText, calibrationState, getAnalyserNode }: VoiceModeProps) => {
  const micStatus = isMuted ? 'muted' : isUserSpeaking ? 'speaking' : 'idle';
  const calibrationLabel = calibrationState.status === 'calibrating'
    ? '噪声校准中'
    : calibrationState.status === 'ready'
      ? '已完成校准'
      : calibrationState.status === 'error'
        ? '使用默认阈值'
        : undefined;
  const calibrationTone = calibrationState.status === 'calibrating'
    ? 'bg-amber-500/20 text-amber-300 border-amber-400/50'
    : calibrationState.status === 'ready'
      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-400/50'
      : 'bg-rose-500/20 text-rose-300 border-rose-400/50';

  return (
    <motion.div
      key="voice"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="h-full flex flex-col items-center justify-center p-8 bg-gradient-to-br from-slate-950 via-indigo-950 to-zinc-950"
    >
      <div className="text-center space-y-12">
        <div className="relative">
          <motion.h1
            animate={{ opacity: [0.03, 0.08, 0.03] }}
            transition={{ repeat: Infinity, duration: 4 }}
            className="text-[12rem] font-black tracking-tighter text-white pointer-events-none select-none leading-none"
          >
            TANK
          </motion.h1>
          <div className="absolute inset-0 flex items-center justify-center">
            <Waveform active={isSpeaking} variant="white" getAnalyserNode={getAnalyserNode} />
          </div>
        </div>

        <div className="space-y-4">
          <p className="text-2xl font-bold text-white/80">
            {isSpeaking ? "TANK 正在回复..." : isAssistantTyping ? "TANK 正在思考..." : isMuted ? "麦克风已静音" : isUserSpeaking ? "正在聆听..." : (statusText || "我在听，请说...")}
          </p>
          {calibrationLabel && (
            <div className="flex justify-center">
              <span className={`inline-flex items-center gap-2 px-3 py-1 text-xs font-semibold rounded-full border ${calibrationTone}`}>
                <span className="h-2 w-2 rounded-full bg-current animate-pulse" />
                {calibrationLabel}
              </span>
            </div>
          )}
          <p className="text-sm text-slate-500 font-medium">
            {"提示：问问我“东京天气”试试看"}
          </p>
        </div>

        <div className="flex justify-center pt-8">
          <div className="relative">
            <motion.button
              whileHover={{ scale: 1.1, boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)" }}
              whileTap={{ scale: 0.9 }}
              animate={micStatus === 'speaking' ? { scale: [1, 1.08, 1], transition: { repeat: Infinity, duration: 1.2 } } : {}}
              onClick={onMicClick}
              className={`w-24 h-24 rounded-full flex items-center justify-center shadow-2xl transition-all ${
                micStatus === 'muted' ? 'bg-slate-700 text-slate-400' :
                micStatus === 'speaking' ? 'bg-red-500 text-white' :
                isAssistantTyping ? 'bg-white/10 text-white/20' :
                'bg-white text-slate-900'
              }`}
            >
              {micStatus === 'muted' ? <MicOff size={40} /> : <Mic size={40} />}
            </motion.button>
            {isSpeaking && (
              <motion.button
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0, opacity: 0 }}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                onClick={onStopSpeaking}
                className="absolute left-full top-1/2 -translate-y-1/2 ml-4 w-16 h-16 rounded-full flex items-center justify-center bg-red-500/20 text-red-400 border border-red-500/30 shadow-lg shadow-red-500/10 transition-all hover:bg-red-500/30"
              >
                <Square size={24} fill="currentColor" />
              </motion.button>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
};
