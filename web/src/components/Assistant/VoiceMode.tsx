import { motion } from 'framer-motion';
import { Mic } from 'lucide-react';
import { Waveform } from './Waveform';

interface VoiceModeProps {
  isAssistantTyping: boolean;
  onMicClick: () => void;
  statusText?: string;
}

export const VoiceMode = ({ isAssistantTyping, onMicClick, statusText }: VoiceModeProps) => {
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
             <Waveform active={isAssistantTyping} variant="white" />
          </div>
        </div>
        
        <div className="space-y-4">
            <p className="text-2xl font-bold text-white/80">
              {isAssistantTyping ? "TANK 正在回复..." : (statusText || "我在听，请说...")}
            </p>
            <p className="text-sm text-slate-500 font-medium">
                提示：问问我“东京天气”试试看
            </p>
        </div>

        <div className="flex gap-4 justify-center pt-8">
            <motion.button 
                whileHover={{ scale: 1.1, boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)" }}
                whileTap={{ scale: 0.9 }}
                onClick={onMicClick}
                className={`w-24 h-24 rounded-full flex items-center justify-center shadow-2xl transition-all ${isAssistantTyping ? 'bg-white/10 text-white/20' : 'bg-white text-slate-900'}`}
            >
                <Mic size={40} />
            </motion.button>
        </div>
      </div>
    </motion.div>
  );
};
