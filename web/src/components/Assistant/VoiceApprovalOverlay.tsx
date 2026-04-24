import { motion, AnimatePresence } from 'framer-motion';
import { ShieldCheck, Check, X } from 'lucide-react';
import type { ApprovalContent } from '../../types/message';

interface VoiceApprovalOverlayProps {
  approval: ApprovalContent | null;
  onRespond: (approvalId: string, approved: boolean) => void;
}

/**
 * Floating approval card for voice mode.
 *
 * Appears below the orb when a tool requires user confirmation.
 * Designed to be unmissable — pulsing amber border, large tap targets,
 * and a clear description of what's being requested.
 */
export const VoiceApprovalOverlay = ({ approval, onRespond }: VoiceApprovalOverlayProps) => {
  return (
    <AnimatePresence>
      {approval && (
        <motion.div
          key={approval.approvalId}
          initial={{ opacity: 0, y: 20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -10, scale: 0.95 }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          className="w-full max-w-sm"
        >
          {/* Outer glow ring */}
          <div className="relative">
            <motion.div
              className="absolute -inset-px rounded-2xl"
              style={{
                background: 'linear-gradient(135deg, rgba(212,160,84,0.4), rgba(212,160,84,0.1), rgba(212,160,84,0.4))',
              }}
              animate={{
                backgroundPosition: ['0% 50%', '100% 50%', '0% 50%'],
              }}
              transition={{ duration: 3, repeat: Infinity, ease: 'linear' }}
            />

            <div className="relative rounded-2xl bg-[#111111] border border-amber-500/20 overflow-hidden">
              {/* Header */}
              <div className="flex items-center gap-2 px-4 py-2.5 border-b border-amber-500/10 bg-amber-500/5">
                <motion.div
                  animate={{ scale: [1, 1.2, 1] }}
                  transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
                >
                  <ShieldCheck size={14} className="text-amber-500" />
                </motion.div>
                <span className="text-[10px] font-mono tracking-widest text-amber-500/80 uppercase">
                  需要确认
                </span>
              </div>

              {/* Body */}
              <div className="px-4 py-3">
                <p className="text-[11px] font-mono text-text-muted mb-1">
                  {approval.toolName}
                </p>
                <p className="text-[13px] text-text-primary leading-relaxed">
                  {approval.description}
                </p>
              </div>

              {/* Actions */}
              <div className="flex gap-2 px-4 pb-4">
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => onRespond(approval.approvalId, true)}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 text-[12px] font-medium tracking-wide transition-colors hover:bg-emerald-500/25"
                >
                  <Check size={14} />
                  批准
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => onRespond(approval.approvalId, false)}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-red-500/10 text-red-400 border border-red-500/20 text-[12px] font-medium tracking-wide transition-colors hover:bg-red-500/20"
                >
                  <X size={14} />
                  拒绝
                </motion.button>
              </div>

              {/* Voice hint */}
              <div className="px-4 pb-3">
                <p className="text-[10px] text-text-muted/60 text-center font-mono">
                  或直接说「同意」/「拒绝」
                </p>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
