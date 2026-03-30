import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { ShieldCheck, Check, X } from 'lucide-react';
import type { ApprovalContent } from '../../types/message';

const APPROVAL_TIMEOUT_MS = 120_000;

type LocalStatus = ApprovalContent['status'];

const STATUS_COLORS: Record<LocalStatus, string> = {
  pending: 'text-amber-500/60',
  approved: 'text-emerald-500/60',
  rejected: 'text-red-500/60',
  expired: 'text-text-muted',
};

interface ApprovalCardProps {
  content: ApprovalContent;
  onRespond: (approvalId: string, approved: boolean) => void;
}

export const ApprovalCard = ({ content, onRespond }: ApprovalCardProps) => {
  // localOverride tracks user clicks and timeout; null means "use prop"
  const [localOverride, setLocalOverride] = useState<LocalStatus | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Effective status: prop wins if non-pending (external resolution), else local override
  const effectiveStatus: LocalStatus =
    content.status !== 'pending' ? content.status : (localOverride ?? 'pending');

  // Auto-expire after timeout
  useEffect(() => {
    if (effectiveStatus !== 'pending') return;

    timerRef.current = setTimeout(() => {
      setLocalOverride('expired');
    }, APPROVAL_TIMEOUT_MS);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [effectiveStatus]);

  const handleApprove = () => {
    if (effectiveStatus !== 'pending') return;
    setLocalOverride('approved');
    onRespond(content.approvalId, true);
  };

  const handleReject = () => {
    if (effectiveStatus !== 'pending') return;
    setLocalOverride('rejected');
    onRespond(content.approvalId, false);
  };

  const isPending = effectiveStatus === 'pending';

  return (
    <div className="w-full max-w-2xl">
      <div className="rounded-2xl rounded-tl-sm bg-surface-raised border border-border-subtle overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border-subtle">
          <ShieldCheck size={12} className="text-amber-500/60" />
          <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase">
            {content.toolName}
          </span>
          <span className="text-[9px] font-mono tracking-wider uppercase ml-auto">
            {isPending ? (
              <motion.span
                className={STATUS_COLORS.pending}
                animate={{ opacity: [0.5, 1, 0.5] }}
                transition={{ repeat: Infinity, duration: 2 }}
              >
                AWAITING APPROVAL
              </motion.span>
            ) : (
              <span className={STATUS_COLORS[effectiveStatus]}>
                {effectiveStatus.toUpperCase()}
              </span>
            )}
          </span>
        </div>

        {/* Body */}
        <div className="p-3 space-y-3">
          <div className="text-[12px] font-mono bg-black/30 text-text-secondary p-3 rounded-xl border border-border-subtle">
            {content.description}
          </div>

          {/* Action buttons — only when pending */}
          {isPending && (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-2"
            >
              <button
                type="button"
                onClick={handleApprove}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors"
              >
                <Check size={12} />
                Approve
              </button>
              <button
                type="button"
                onClick={handleReject}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-mono bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors"
              >
                <X size={12} />
                Reject
              </button>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
};
