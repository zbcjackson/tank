import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Settings, Check, Zap, ZapOff } from 'lucide-react';

import type { ListenMode } from '../../hooks/useListenMode';

interface ListenModeSettingsProps {
  listenMode: ListenMode;
  voiceInterruptEnabled: boolean;
  wakeWordAvailable: boolean;
  onListenModeChange: (mode: ListenMode) => void;
  onVoiceInterruptEnabledChange: (enabled: boolean) => void;
  className?: string;
  popoverPosition?: 'above' | 'below';
}

const dropdownVariants = {
  hidden: { opacity: 0, y: 4, scale: 0.97 },
  visible: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: 4, scale: 0.97 },
};

interface ModeOption {
  value: ListenMode;
  label: string;
  description: string;
  requiresWakeWord?: boolean;
}

const ALL_MODES: ModeOption[] = [
  {
    value: 'continuous',
    label: '持续聆听',
    description: '麦克风始终开启，可随时打断',
  },
  {
    value: 'wake_word',
    label: '唤醒词',
    description: '说出唤醒词后开始对话',
    requiresWakeWord: true,
  },
  {
    value: 'ptt',
    label: '按键说话',
    description: '点击麦克风开始录音，再次点击发送',
  },
];

export const ListenModeSettings = ({
  listenMode,
  voiceInterruptEnabled,
  wakeWordAvailable,
  onListenModeChange,
  onVoiceInterruptEnabledChange,
  className = '',
  popoverPosition = 'above',
}: ListenModeSettingsProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const visibleModes = ALL_MODES.filter((m) => !m.requiresWakeWord || wakeWordAvailable);

  const popoverPositionClass =
    popoverPosition === 'above' ? 'bottom-full mb-2' : 'top-full mt-2';

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        aria-label="语音模式设置"
        aria-expanded={isOpen}
        data-testid="listen-mode-settings-button"
        className="w-9 h-9 rounded-xl flex items-center justify-center text-text-muted hover:text-amber-400 hover:bg-amber-500/10 border border-border-subtle hover:border-amber-500/15 transition-all"
      >
        <Settings size={15} />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            variants={dropdownVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            transition={{ duration: 0.15, ease: [0.23, 1, 0.32, 1] }}
            data-testid="listen-mode-settings-popover"
            className={`absolute ${popoverPositionClass} right-0 min-w-[280px] py-2 bg-surface-overlay border border-border-subtle rounded-xl shadow-[0_8px_32px_rgba(0,0,0,0.5)] z-30 backdrop-blur-sm`}
          >
            <div className="px-3 pt-1 pb-2">
              <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase">
                Listen Mode
              </span>
            </div>

            {visibleModes.map((mode) => (
              <button
                key={mode.value}
                type="button"
                data-testid={`listen-mode-option-${mode.value}`}
                onClick={() => {
                  onListenModeChange(mode.value);
                }}
                className="w-full px-3 py-2 text-left hover:bg-white/[0.04] transition-colors flex items-start justify-between gap-2 group/item"
              >
                <div className="flex flex-col gap-0.5">
                  <span className="text-[13px] text-text-primary">{mode.label}</span>
                  <span className="text-[11px] text-text-muted leading-snug">
                    {mode.description}
                  </span>
                </div>
                {listenMode === mode.value && (
                  <Check size={13} className="text-amber-500/70 mt-1 shrink-0" />
                )}
              </button>
            ))}

            {listenMode === 'wake_word' && (
              <>
                <div className="my-1.5 mx-3 h-px bg-border-subtle/50" />
                <button
                  type="button"
                  onClick={() => onVoiceInterruptEnabledChange(!voiceInterruptEnabled)}
                  data-testid="voice-interrupt-toggle"
                  className="w-full px-3 py-2 text-left hover:bg-white/[0.04] transition-colors flex items-center justify-between gap-2"
                >
                  <div className="flex items-center gap-2">
                    {voiceInterruptEnabled ? (
                      <Zap size={14} className="text-amber-500/70 shrink-0" />
                    ) : (
                      <ZapOff size={14} className="text-text-muted shrink-0" />
                    )}
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[13px] text-text-primary">回复时无需唤醒词</span>
                      <span className="text-[11px] text-text-muted leading-snug">
                        {voiceInterruptEnabled
                          ? '回复中可直接说话打断'
                          : '回复中仍需说唤醒词才能打断'}
                      </span>
                    </div>
                  </div>
                  <span
                    className={`relative w-8 h-4 rounded-full transition-colors ${voiceInterruptEnabled ? 'bg-amber-500/40' : 'bg-zinc-700'}`}
                  >
                    <span
                      className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${voiceInterruptEnabled ? 'left-4' : 'left-0.5'}`}
                    />
                  </span>
                </button>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
