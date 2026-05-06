/**
 * Floating indicator that appears while channel audio is playing.
 *
 * Shows the channel slug and an X button to stop the audio.
 * Positioned top-left so it doesn't clash with the conversation-list button (top-right)
 * or the voice/chat mode UI (centered).
 */
import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Volume2, X } from 'lucide-react';

interface ChannelAudioIndicatorProps {
  slug: string | null;
  onStop: () => void;
}

export const ChannelAudioIndicator: React.FC<ChannelAudioIndicatorProps> = ({ slug, onStop }) => {
  return (
    <AnimatePresence>
      {slug && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.15 }}
          className="absolute top-3 left-3 z-30 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-600/20 border border-blue-500/40 backdrop-blur-sm"
          data-testid="channel-audio-indicator"
        >
          <Volume2 size={14} className="text-blue-300 animate-pulse" />
          <span className="text-xs font-medium text-blue-200">
            Playing <span className="font-mono">#{slug}</span>
          </span>
          <button
            onClick={onStop}
            className="p-0.5 rounded hover:bg-blue-500/30 text-blue-200 hover:text-white transition-colors"
            title="Stop channel audio"
            aria-label="Stop channel audio"
            data-testid="channel-audio-stop"
          >
            <X size={14} />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
