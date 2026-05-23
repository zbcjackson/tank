import { useState } from 'react';
import { motion } from 'framer-motion';
import { Server, Loader2, AlertCircle } from 'lucide-react';

const CARD_VARIANTS = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0 },
};

interface ServerSettingsProps {
  isProbing: boolean;
  probeError: string | null;
  currentHostPort: string;
  onSave: (hostPort: string) => Promise<boolean>;
}

export const ServerSettingsPanel = ({
  isProbing,
  probeError,
  currentHostPort,
  onSave,
}: ServerSettingsProps) => {
  const [input, setInput] = useState(currentHostPort);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isProbing && input.trim()) {
      onSave(input.trim());
    }
  };

  return (
    <div className="h-screen w-full flex items-center justify-center" style={{ background: '#0a0a0a' }}>
      <motion.div
        variants={CARD_VARIANTS}
        initial="hidden"
        animate="visible"
        transition={{ duration: 0.25 }}
        className="w-full max-w-sm mx-4 p-6 rounded-2xl bg-surface-raised border border-border-subtle shadow-2xl shadow-black/50"
      >
        <div className="flex items-center gap-3 mb-5">
          <div className="p-2.5 rounded-xl bg-amber-500/10">
            <Server className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <h2 className="text-text-primary text-sm font-medium">Connect to Server</h2>
            <p className="text-text-muted text-xs mt-0.5">Enter the backend address to get started</p>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="192.168.1.50:8000"
            disabled={isProbing}
            autoFocus
            className="w-full px-3.5 py-2.5 rounded-lg bg-white/5 border border-border-subtle text-text-primary text-sm placeholder:text-text-muted/50 focus:outline-none focus:border-amber-500/40 focus:ring-1 focus:ring-amber-500/20 transition-colors disabled:opacity-50"
          />

          {probeError && (
            <div className="flex items-start gap-2 mt-3 text-red-400/80">
              <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
              <p className="text-xs">{probeError}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={isProbing || !input.trim()}
            className="w-full mt-4 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {isProbing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Detecting...
              </>
            ) : (
              'Connect'
            )}
          </button>
        </form>
      </motion.div>
    </div>
  );
};
