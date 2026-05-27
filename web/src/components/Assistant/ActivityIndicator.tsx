import { motion, AnimatePresence } from 'framer-motion';
import { Circle, Wrench, MessageSquare, Volume2, AlertCircle, XCircle } from 'lucide-react';
import type { AssistantStatus } from '../../hooks/useAssistant';

interface ActivityIndicatorProps {
  status: AssistantStatus;
}

const STATUS_CONFIG: Record<
  Exclude<AssistantStatus, 'idle'>,
  { icon: React.ReactNode; text: string; colorClass: string }
> = {
  thinking: { icon: <Circle size={14} />, text: '思考中...', colorClass: 'text-amber-500' },
  tool_calling: { icon: <Wrench size={14} />, text: '工作中...', colorClass: 'text-blue-500' },
  responding: { icon: <MessageSquare size={14} />, text: '回复中...', colorClass: 'text-green-500' },
  speaking: { icon: <Volume2 size={14} />, text: '播放中...', colorClass: 'text-purple-500' },
  interrupted: { icon: <AlertCircle size={14} />, text: '已中断', colorClass: 'text-orange-500' },
  error: { icon: <XCircle size={14} />, text: '出错了', colorClass: 'text-red-500' },
};

export const ActivityIndicator = ({ status }: ActivityIndicatorProps) => {
  if (status === 'idle') return null;

  const config = STATUS_CONFIG[status];

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={status}
        initial={{ opacity: 0, x: -4 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -4 }}
        transition={{ duration: 0.2 }}
        className="flex items-center gap-1.5 py-1"
      >
        <motion.div
          animate={{
            scale: [1, 1.1, 1],
            opacity: [0.6, 1, 0.6],
          }}
          transition={{
            repeat: Infinity,
            duration: 1.5,
            ease: 'easeInOut',
          }}
          className={config.colorClass}
        >
          {config.icon}
        </motion.div>
        <span className="text-[10px] text-text-muted whitespace-nowrap">{config.text}</span>
      </motion.div>
    </AnimatePresence>
  );
};
