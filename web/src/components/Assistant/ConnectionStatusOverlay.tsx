import { motion } from 'framer-motion';
import { useState, useEffect, useRef } from 'react';
import { WifiOff, RefreshCw, RotateCw, AlertCircle, Clock } from 'lucide-react';
import type { ConnectionState, ConnectionMetadata } from '../../services/websocket';

interface Props {
  state: ConnectionState;
  metadata: ConnectionMetadata;
  onReconnect: () => void;
}

export const ConnectionStatusOverlay = ({ state, metadata, onReconnect }: Props) => {
  const [countdown, setCountdown] = useState<number>(0);
  const startTimeRef = useRef<number>(0);
  const initialDelayRef = useRef<number>(0);

  // Update refs when metadata changes (new reconnect attempt)
  useEffect(() => {
    if (state === 'reconnecting' && metadata.nextRetryIn) {
      startTimeRef.current = Date.now();
      initialDelayRef.current = metadata.nextRetryIn;
    }
  }, [state, metadata.nextRetryIn]);

  // Tick the countdown timer
  useEffect(() => {
    if (state === 'reconnecting' && initialDelayRef.current > 0) {
      const updateCountdown = () => {
        const elapsed = Date.now() - startTimeRef.current;
        const remaining = Math.max(0, Math.ceil((initialDelayRef.current - elapsed) / 1000));
        setCountdown(remaining);
      };

      updateCountdown(); // Initial update
      const interval = setInterval(updateCountdown, 1000);

      return () => clearInterval(interval);
    }
  }, [state]);

  if (state !== 'reconnecting' && state !== 'failed') {
    return null;
  }

  // Get icon based on error type
  const getIcon = () => {
    if (state === 'failed') {
      return <WifiOff className="w-6 h-6 text-red-400" />;
    }

    if (metadata.errorType === 'timeout') {
      return (
        <motion.div animate={{ scale: [1, 1.1, 1] }} transition={{ duration: 2, repeat: Infinity }}>
          <Clock className="w-6 h-6 text-yellow-400" />
        </motion.div>
      );
    }

    if (metadata.errorType === 'server') {
      return <AlertCircle className="w-6 h-6 text-orange-400" />;
    }

    return (
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
      >
        <RefreshCw className="w-6 h-6 text-blue-400" />
      </motion.div>
    );
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      className="fixed bottom-6 right-6 z-50 bg-slate-900/95 backdrop-blur-md border border-slate-700 rounded-2xl shadow-2xl p-6 max-w-sm"
    >
      <div className="flex items-start gap-4">
        <div className="flex-shrink-0">{getIcon()}</div>

        <div className="flex-1">
          {state === 'reconnecting' && (
            <>
              <h3 className="text-white font-semibold mb-1">正在重新连接...</h3>
              <p className="text-slate-400 text-sm mb-1">
                尝试 {metadata.attempt}/{metadata.maxAttempts}
                {countdown > 0 && ` · ${countdown}秒后重试`}
              </p>
              {metadata.error && <p className="text-slate-500 text-xs mb-3">{metadata.error}</p>}
              <button
                onClick={onReconnect}
                className="flex items-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white text-sm font-medium rounded-lg transition-colors"
              >
                <RotateCw className="w-4 h-4" />
                立即重连
              </button>
            </>
          )}

          {state === 'failed' && (
            <>
              <h3 className="text-white font-semibold mb-1">连接失败</h3>
              <p className="text-slate-400 text-sm mb-3">
                {metadata.error || '无法连接到服务器，请检查网络或稍后重试'}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={onReconnect}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white text-sm font-medium rounded-lg transition-colors"
                >
                  <RotateCw className="w-4 h-4" />
                  重新连接
                </button>
                <button
                  onClick={() => window.location.reload()}
                  className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm font-medium rounded-lg transition-colors"
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
