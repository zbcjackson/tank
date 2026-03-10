import { motion, AnimatePresence } from 'framer-motion';
import { MessageSquare, AudioLines } from 'lucide-react';

interface ModeToggleProps {
  mode: 'voice' | 'chat';
  onToggle: () => void;
}

export const ModeToggle = ({ mode, onToggle }: ModeToggleProps) => {
  return (
    <motion.button
      initial={{ scale: 0, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ delay: 0.3, type: 'spring', stiffness: 200, damping: 20 }}
      whileHover={{ scale: 1.06 }}
      whileTap={{ scale: 0.94 }}
      onClick={onToggle}
      className="fixed bottom-8 right-8 w-12 h-12 rounded-full flex items-center justify-center z-50 bg-surface-raised border border-border-subtle text-text-secondary hover:text-amber-400 hover:border-amber-500/20 transition-all duration-300 shadow-lg shadow-black/30"
    >
      <AnimatePresence mode="wait">
        {mode === 'voice' ? (
          <motion.div
            key="chat-icon"
            initial={{ rotate: -90, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            exit={{ rotate: 90, opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            <MessageSquare size={18} />
          </motion.div>
        ) : (
          <motion.div
            key="voice-icon"
            initial={{ rotate: -90, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            exit={{ rotate: 90, opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            <AudioLines size={18} />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.button>
  );
};
