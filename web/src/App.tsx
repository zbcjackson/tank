import { useState, useEffect, useRef, useCallback } from 'react';
import { useAssistant } from './hooks/useAssistant';
import { VoiceMode } from './components/Assistant/VoiceMode';
import { ChatMode } from './components/Assistant/ChatMode';
import { ModeToggle } from './components/Assistant/ModeToggle';
import { ConnectionStatusOverlay } from './components/Assistant/ConnectionStatusOverlay';
import { SessionList } from './components/Assistant/SessionList';
import { AnimatePresence } from 'framer-motion';
import { Menu } from 'lucide-react';
import type { WakeWordDetector } from './services/wakeWordDetector';
import { createWakeWordDetector, type WakeWordEngine } from './services/wakeWordFactory';

const SESSION_ID = Math.random().toString(36).substring(7);
const APP_BG_STYLE = { background: '#0a0a0a' };

const WAKE_WORD_ENABLED = import.meta.env.VITE_WAKE_WORD_ENABLED === 'true';
const WAKE_WORD_ENGINE = (import.meta.env.VITE_WAKE_WORD_ENGINE || 'sherpa-onnx') as WakeWordEngine;

function useWakeWordDetector(): WakeWordDetector | null {
  const [detector, setDetector] = useState<WakeWordDetector | null>(null);
  const detectorRef = useRef<WakeWordDetector | null>(null);

  useEffect(() => {
    if (!WAKE_WORD_ENABLED) return;

    let cancelled = false;

    createWakeWordDetector({ engine: WAKE_WORD_ENGINE })
      .then((d) => {
        if (cancelled) {
          d.release();
        } else {
          console.log(`Wake word detector loaded successfully (engine=${WAKE_WORD_ENGINE})`);
          detectorRef.current = d;
          setDetector(d);
        }
      })
      .catch((err) => {
        console.warn('Wake word detector failed to load, falling back to always-on mode:', err);
      });

    return () => {
      cancelled = true;
      detectorRef.current?.release();
      detectorRef.current = null;
    };
  }, []);

  return detector;
}

function App() {
  const wakeWordDetector = useWakeWordDetector();
  const [sessionListOpen, setSessionListOpen] = useState(false);
  const [activeContextSessionId, setActiveContextSessionId] = useState<string | null>(null);

  const {
    steps,
    mode,
    assistantStatus,
    connectionState,
    connectionMetadata,
    sendMessage,
    respondToApproval,
    toggleMode,
    toggleMute,
    isMuted,
    getAnalyserNode,
    stopSpeaking,
    manualReconnect,
    pauseAudioCapture,
    resumeAudioCapture,
    resumeSession,
    newSession,
    capabilities,
    conversationState,
    wakeWordKeyword,
    ttsRms,
  } = useAssistant(SESSION_ID, wakeWordDetector);

  const handleSelectSession = useCallback(
    async (contextSessionId: string) => {
      setSessionListOpen(false);
      setActiveContextSessionId(contextSessionId);
      await resumeSession(contextSessionId);
    },
    [resumeSession],
  );

  const handleNewSession = useCallback(() => {
    setSessionListOpen(false);
    setActiveContextSessionId(null);
    newSession();
  }, [newSession]);

  const statusText = connectionState === 'connected' ? undefined : `Status: ${connectionState}`;

  return (
    <div className="h-screen w-full flex flex-col overflow-hidden relative" style={APP_BG_STYLE}>
      <ConnectionStatusOverlay
        state={connectionState}
        metadata={connectionMetadata}
        onReconnect={manualReconnect}
      />

      {/* Session list sidebar */}
      <SessionList
        open={sessionListOpen}
        onClose={() => setSessionListOpen(false)}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        activeSessionId={activeContextSessionId}
      />

      {/* Session list toggle button */}
      <button
        onClick={() => setSessionListOpen(true)}
        className="absolute top-3 right-3 z-30 p-2 rounded-lg bg-neutral-800/60 hover:bg-neutral-700/80 text-neutral-400 hover:text-neutral-200 transition-colors backdrop-blur-sm"
        title="Sessions"
      >
        <Menu size={18} />
      </button>

      <main className="flex-1 relative overflow-hidden">
        <AnimatePresence mode="wait">
          {mode === 'voice' ? (
            <VoiceMode
              assistantStatus={assistantStatus}
              isMuted={isMuted}
              onMicClick={toggleMute}
              onStopSpeaking={stopSpeaking}
              statusText={statusText}
              getAnalyserNode={getAnalyserNode}
              conversationState={conversationState}
              wakeWordKeyword={wakeWordKeyword}
              ttsRms={ttsRms}
            />
          ) : (
            <ChatMode
              messages={steps}
              assistantStatus={assistantStatus}
              onSendMessage={sendMessage}
              onStopSpeaking={stopSpeaking}
              onApprovalRespond={respondToApproval}
              pauseAudioCapture={pauseAudioCapture}
              resumeAudioCapture={resumeAudioCapture}
            />
          )}
        </AnimatePresence>
      </main>

      {capabilities.asr && <ModeToggle mode={mode} onToggle={toggleMode} />}
    </div>
  );
}

export default App;
