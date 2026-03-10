import { motion } from 'framer-motion';
import { useState, useEffect, useRef } from 'react';
import { WifiOff, RefreshCw, RotateCw, AlertCircle, Clock } from 'lucide-react';
import type { ConnectionState, ConnectionMetadata } from '../../services/websocket';

const TIMEOUT_ANIMATE = { scale: [1, 1.1, 1] };
const TIMEOUT_TRANSITION = { duration: 2, repeat: Infinity };
const SPIN_ANIMATE = { rotate: 360 };
const SPIN_TRANSITION = { duration: 2, repeat: Infinity, ease: 'linear' as const };
const OVERLAY_INITIAL = { opacity: 0, y: 10 };
const OVERLAY_ANIMATE = { opacity: 1, y: 0 };
const OVERLAY_EXIT = { opacity: 0, y: 10 };

const RECONNECT_BTN_CLASS =
  'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-colors';

interface Props {
  state: ConnectionState;
  metadata: ConnectionMetadata;
  onReconnect: () => void;
}

export const ConnectionStatusOverlay = ({ state, metadata, onReconnect }: Props) => {
  const [countdown, setCountdown] = useState<number>(0);
  const startTimeRef = useRef<number>(0);
  const initialDelayRef = useRef<number>(0);

  useEffect(() => {
    if (state === 'reconnecting' && metadata.nextRetryIn) {
      startTimeRef.current = Date.now();
      initialDelayRef.current = metadata.nextRetryIn;
    }
  }, [state, metadata.nextRetryIn]);

  useEffect(() => {
    if (state === 'reconnecting' && initialDelayRef.current > 0) {
      const updateCountdown = () => {
        const elapsed = Date.now() - startTimeRef.current;
        const remaining = Math.max(0, Math.ceil((initialDelayRef.current - elapsed) / 1000));
        setCountdown(remaining);
      };

      updateCountdown();
      const interval = setInterval(updateCountdown, 1000);
      return () => clearInterval(interval);
    }
  }, [state]);

  if (state !== 'reconnecting' && state !== 'failed') {
    return null;
  }

  const getIcon = () => {
    if (state === 'failed') {
      return <WifiOff className="w-5 h-5 text-red-400/80" />;
    }
    if (metadata.errorType === 'timeout') {
      return (
        <motion.div animate={TIMEOUT_ANIMATE} transition={TIMEOUT_TRANSITION}>
          <Clock className="w-5 h-5 text-amber-400/80" />
        </motion.div>
      );
    }
    if (metadata.errorType === 'server') {
      return <AlertCircle className="w-5 h-5 text-orange-400/80" />;
    }
    return (
      <motion.div animate={SPIN_ANIMATE} transition={SPIN_TRANSITION}>
        <RefreshCw className="w-5 h-5 text-amber-400/80" />
      </motion.div>
    );
  };

  return (
    <motion.div
      initial={OVERLAY_INITIAL}
      animate={OVERLAY_ANIMATE}
      exit={OVERLAY_EXIT}
      className="fixed bottom-6 right-6 z-50 rounded-2xl p-5 max-w-sm bg-surface-raised border border-border-subtle shadow-2xl shadow-black/50"
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 mt-0.5">{getIcon()}</div>

        <div className="flex-1">
          {state === 'reconnecting' && (
            <>
              <h3 className="text-text-primary text-sm font-medium mb-1">正在重新连接</h3>
              <p className="text-text-muted text-xs mb-1">
                尝试 {metadata.attempt}/{metadata.maxAttempts}
                {countdown > 0 && ` · ${countdown}秒后重试`}
              </p>
              {metadata.error && (
                <p className="text-text-muted/60 text-[11px] mb-3">{metadata.error}</p>
              )}
              <button onClick={onReconnect} className={RECONNECT_BTN_CLASS}>
                <RotateCw className="w-3 h-3" />
                立即重连
              </button>
            </>
          )}

          {state === 'failed' && (
            <>
              <h3 className="text-text-primary text-sm font-medium mb-1">连接失败</h3>
              <p className="text-text-muted text-xs mb-3">{metadata.error || '无法连接到服务器'}</p>
              <div className="flex gap-2">
                <button onClick={onReconnect} className={RECONNECT_BTN_CLASS}>
                  <RotateCw className="w-3 h-3" />
                  重新连接
                </button>
                <button
                  onClick={() => window.location.reload()}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg bg-white/5 text-text-secondary border border-border-subtle hover:bg-white/8 transition-colors"
                >
                  刷新页面
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </motion.div>
  );
};
