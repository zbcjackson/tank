import { motion, AnimatePresence } from 'framer-motion';
import { MessageSquare, Volume2 } from 'lucide-react';

interface ModeToggleProps {
  mode: 'voice' | 'chat';
  onToggle: () => void;
}

export const ModeToggle = ({ mode, onToggle }: ModeToggleProps) => {
  return (
    <motion.button 
      initial={{ scale: 0 }}
      animate={{ scale: 1 }}
      whileHover={{ scale: 1.1 }}
      whileTap={{ scale: 0.9 }}
      onClick={onToggle}
      className={`fixed bottom-8 right-8 w-14 h-14 rounded-full shadow-2xl border flex items-center justify-center z-50 transition-all duration-500 ${mode === 'voice' ? 'bg-white/10 text-white border-white/20 backdrop-blur-md hover:bg-white/20' : 'bg-white dark:bg-zinc-800 text-primary border-slate-200 dark:border-zinc-700 hover:bg-slate-50 dark:hover:bg-zinc-700'}`}
    >
      <AnimatePresence mode="wait">
        {mode === 'voice' ? (
          <motion.div
            key="chat-icon"
            initial={{ rotate: -90, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            exit={{ rotate: 90, opacity: 0 }}
          >
            <MessageSquare size={24} />
          </motion.div>
        ) : (
          <motion.div
            key="voice-icon"
            initial={{ rotate: -90, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            exit={{ rotate: 90, opacity: 0 }}
          >
            <Volume2 size={24} />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.button>
  );
};
