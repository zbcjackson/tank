import { motion } from 'framer-motion';
import { Mic, Send } from 'lucide-react';

interface PttButtonProps {
  isRecording: boolean;
  onStart: () => void;
  onStop: () => void;
  size?: 'sm' | 'lg';
}

/**
 * Push-to-talk button. Tap once to begin recording, tap again to send.
 *
 * Rendered in two sizes:
 *   - `lg` (default): voice mode primary control (64px round).
 *   - `sm`: chat-mode inline input control (36px square).
 */
export const PttButton = ({ isRecording, onStart, onStop, size = 'lg' }: PttButtonProps) => {
  const isLg = size === 'lg';
  const dimensions = isLg ? 'w-16 h-16 rounded-full' : 'w-9 h-9 rounded-xl';
  const icon = isRecording ? <Send size={isLg ? 22 : 14} /> : <Mic size={isLg ? 24 : 14} />;

  const colorClass = isRecording
    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-[0_0_30px_rgba(212,160,84,0.18)]'
    : 'bg-zinc-800/40 text-zinc-300 border border-zinc-700/60 hover:bg-zinc-800/70';

  const handleClick = () => {
    if (isRecording) onStop();
    else onStart();
  };

  return (
    <motion.button
      type="button"
      whileHover={{ scale: 1.06 }}
      whileTap={{ scale: 0.94 }}
      onClick={handleClick}
      aria-label={isRecording ? '发送录音' : '开始录音'}
      aria-pressed={isRecording}
      data-testid="ptt-button"
      data-recording={isRecording ? 'true' : 'false'}
      className={`${dimensions} flex items-center justify-center transition-all duration-200 ${colorClass}`}
    >
      {icon}
    </motion.button>
  );
};
