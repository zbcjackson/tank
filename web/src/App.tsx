import { useState, useEffect, useRef } from 'react';
import { useAssistant } from './hooks/useAssistant';
import { VoiceMode } from './components/Assistant/VoiceMode';
import { ChatMode } from './components/Assistant/ChatMode';
import { ModeToggle } from './components/Assistant/ModeToggle';
import { ConnectionStatusOverlay } from './components/Assistant/ConnectionStatusOverlay';
import { AnimatePresence } from 'framer-motion';
import type { WakeWordDetector } from './services/wakeWordDetector';
import { PorcupineDetector } from './services/porcupineDetector';

const SESSION_ID = Math.random().toString(36).substring(7);
const APP_BG_STYLE = { background: '#0a0a0a' };

const WAKE_WORD_ENABLED = import.meta.env.VITE_WAKE_WORD_ENABLED === 'true';
const PORCUPINE_ACCESS_KEY = import.meta.env.VITE_PORCUPINE_ACCESS_KEY || '';

if (WAKE_WORD_ENABLED && !PORCUPINE_ACCESS_KEY) {
  console.error('VITE_PORCUPINE_ACCESS_KEY is required when wake word is enabled');
}

function useWakeWordDetector(): WakeWordDetector | null {
  const [detector, setDetector] = useState<WakeWordDetector | null>(null);
  const detectorRef = useRef<WakeWordDetector | null>(null);

  useEffect(() => {
    if (!WAKE_WORD_ENABLED || !PORCUPINE_ACCESS_KEY) return;

    let cancelled = false;

    PorcupineDetector.create({
      accessKey: PORCUPINE_ACCESS_KEY,
      keyword: {
        publicPath: '/models/tank_wake_word.ppn',
        label: 'Hey Tank',
      },
      model: {
        publicPath: '/models/porcupine_params.pv',
      },
    })
      .then((d) => {
        if (cancelled) {
          d.release();
        } else {
          console.log('Wake word detector loaded successfully');
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

  const {
    steps,
    mode,
    assistantStatus,
    connectionState,
    connectionMetadata,
    sendMessage,
    toggleMode,
    toggleMute,
    isMuted,
    getAnalyserNode,
    stopSpeaking,
    manualReconnect,
    pauseAudioCapture,
    resumeAudioCapture,
    capabilities,
    conversationState,
    ttsRms,
  } = useAssistant(SESSION_ID, wakeWordDetector);

  const statusText = connectionState === 'connected' ? undefined : `Status: ${connectionState}`;

  return (
    <div className="h-screen w-full flex flex-col overflow-hidden relative" style={APP_BG_STYLE}>
      <ConnectionStatusOverlay
        state={connectionState}
        metadata={connectionMetadata}
        onReconnect={manualReconnect}
      />

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
              ttsRms={ttsRms}
            />
          ) : (
            <ChatMode
              messages={steps}
              assistantStatus={assistantStatus}
              onSendMessage={sendMessage}
              onStopSpeaking={stopSpeaking}
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
