import { AnimatePresence, motion } from 'framer-motion';
import type { BackgroundTask } from '../../hooks/useActiveBackgroundTasks';

interface BackgroundTaskOverlayProps {
  tasks: BackgroundTask[];
}

const overlayVariants = {
  hidden: { opacity: 0, x: -12 },
  visible: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -12 },
};

export const BackgroundTaskOverlay = ({ tasks }: BackgroundTaskOverlayProps) => {
  return (
    <AnimatePresence>
      {tasks.length > 0 && (
        <motion.div
          variants={overlayVariants}
          initial="hidden"
          animate="visible"
          exit="exit"
          transition={{ duration: 0.25, ease: 'easeOut' }}
          className="absolute left-3 top-1/2 -translate-y-1/2 z-10 pointer-events-none"
        >
          <div className="bg-black/70 backdrop-blur-sm border border-white/10 rounded-xl px-3 py-2.5 min-w-[140px] max-w-[180px]">
            <div className="space-y-2">
              {tasks.map((task) => (
                <TaskRow key={task.stepId} task={task} />
              ))}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

const TaskRow = ({ task }: { task: BackgroundTask }) => {
  const latestActivity = task.activities.length > 0
    ? task.activities[task.activities.length - 1]
    : null;

  return (
    <div className="space-y-0.5">
      <div className="flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-purple-400 shrink-0 animate-pulse" />
        <span className="text-[11px] font-mono text-purple-300 truncate">
          {task.agentType}
        </span>
      </div>
      {task.description && (
        <div className="pl-3">
          <span className="text-[10px] font-mono text-white/40 truncate block">
            {task.description}
          </span>
        </div>
      )}
      {latestActivity && (
        <div className="flex items-center gap-1.5 pl-3">
          <span className="text-[10px] font-mono text-white/50 truncate">
            {latestActivity.name}
          </span>
          <span className={`text-[10px] shrink-0 ${latestActivity.done ? 'text-emerald-400' : 'text-purple-400'}`}>
            {latestActivity.done ? '✓' : '⟳'}
          </span>
        </div>
      )}
    </div>
  );
};
