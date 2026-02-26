import { motion } from 'framer-motion';
import { Mic, MicOff, Square } from 'lucide-react';
import { Waveform } from './Waveform';

interface VoiceModeProps {
  isAssistantTyping: boolean;
  isUserSpeaking: boolean;
  isMuted: boolean;
  isSpeaking: boolean;
  onMicClick: () => void;
  onStopSpeaking: () => void;
  statusText?: string;
  getAnalyserNode?: () => AnalyserNode | null;
}

export const VoiceMode = ({ isAssistantTyping, isUserSpeaking, isMuted, isSpeaking, onMicClick, onStopSpeaking, statusText, getAnalyserNode }: VoiceModeProps) => {
  const micStatus = isMuted ? 'muted' : isUserSpeaking ? 'speaking' : 'idle';

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
            {isSpeaking ? "TANK \u6b63\u5728\u56de\u590d..." : isAssistantTyping ? "TANK \u6b63\u5728\u601d\u8003..." : isMuted ? "\u9ea6\u514b\u98ce\u5df2\u9759\u97f3" : isUserSpeaking ? "\u6b63\u5728\u8046\u542c..." : (statusText || "\u6211\u5728\u542c\uff0c\u8bf7\u8bf4...")}
          </p>
          <p className="text-sm text-slate-500 font-medium">
            {"\u63d0\u793a\uff1a\u95ee\u95ee\u6211\u201c\u4e1c\u4eac\u5929\u6c14\u201d\u8bd5\u8bd5\u770b"}
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
