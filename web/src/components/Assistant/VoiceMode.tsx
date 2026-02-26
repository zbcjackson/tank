import { motion } from 'framer-motion';
import { Mic, MicOff } from 'lucide-react';
import { Waveform } from './Waveform';

interface VoiceModeProps {
  isAssistantTyping: boolean;
  isUserSpeaking: boolean;
  isMuted: boolean;
  onMicClick: () => void;
  statusText?: string;
  getAnalyserNode?: () => AnalyserNode | null;
}

export const VoiceMode = ({ isAssistantTyping, isUserSpeaking, isMuted, onMicClick, statusText, getAnalyserNode }: VoiceModeProps) => {
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
            <Waveform active={isAssistantTyping} variant="white" getAnalyserNode={getAnalyserNode} />
          </div>
        </div>

        <div className="space-y-4">
          <p className="text-2xl font-bold text-white/80">
            {isAssistantTyping ? "TANK \u6b63\u5728\u56de\u590d..." : isMuted ? "\u9ea6\u514b\u98ce\u5df2\u9759\u97f3" : isUserSpeaking ? "\u6b63\u5728\u8046\u542c..." : (statusText || "\u6211\u5728\u542c\uff0c\u8bf7\u8bf4...")}
          </p>
          <p className="text-sm text-slate-500 font-medium">
            {"\u63d0\u793a\uff1a\u95ee\u95ee\u6211\u201c\u4e1c\u4eac\u5929\u6c14\u201d\u8bd5\u8bd5\u770b"}
          </p>
        </div>

        <div className="flex gap-4 justify-center pt-8">
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
        </div>
      </div>
    </motion.div>
  );
};
