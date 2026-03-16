import { motion } from 'framer-motion';

interface WakeWordIndicatorProps {
  keyword: string;
}

export const WakeWordIndicator = ({ keyword }: WakeWordIndicatorProps) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.4 }}
      data-testid="wake-word-indicator"
      className="flex flex-col items-center gap-2"
    >
      <p className="text-sm text-text-secondary tracking-wide">
        说 "<span className="text-amber-400 font-medium">{keyword}</span>" 开始对话
      </p>
      <p className="text-xs text-text-muted/50">Say "{keyword}" to start</p>
    </motion.div>
  );
};
