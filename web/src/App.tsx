import { useState, useEffect } from 'react';
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

function useWakeWordDetector(): WakeWordDetector | null {
  const [detector, setDetector] = useState<WakeWordDetector | null>(null);

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
          setDetector(d);
        }
      })
      .catch((err) => {
        console.warn('Wake word detector failed to load, falling back to always-on mode:', err);
      });

    return () => {
      cancelled = true;
      setDetector((prev) => {
        prev?.release();
        return null;
      });
    };
  }, []);

  return detector;
}

function App() {
  const wakeWordDetector = useWakeWordDetector();

  const {
    steps,
    mode,
    isAssistantTyping,
    isSpeaking,
    isUserSpeaking,
    connectionState,
    connectionMetadata,
    sendMessage,
    toggleMode,
    toggleMute,
    isMuted,
    getAnalyserNode,
    stopSpeaking,
    calibrationState,
    manualReconnect,
    pauseAudioCapture,
    resumeAudioCapture,
    capabilities,
    conversationState,
  } = useAssistant(SESSION_ID, wakeWordDetector);

  let calibrationStatusText: string | undefined;
  if (calibrationState.status === 'calibrating') {
    calibrationStatusText = '正在校准背景噪声...';
  } else if (calibrationState.status === 'error') {
    calibrationStatusText = '噪声校准失败，使用默认阈值';
  }
  const statusText =
    calibrationStatusText ||
    (connectionState === 'connected' ? undefined : `Status: ${connectionState}`);

  return (
    <div className="h-screen w-full flex flex-col overflow-hidden relative" style={APP_BG_STYLE}>
      {connectionState === 'failed' && calibrationState.status === 'error' && (
        <div className="absolute inset-0 z-[100] flex items-center justify-center bg-black/90 backdrop-blur-md p-8 text-center">
          <div className="max-w-md">
            <h2 className="text-xl font-semibold text-text-primary mb-2">连接错误</h2>
            <p className="text-text-secondary text-sm mb-6">
              无法启动麦克风或连接到服务器，请检查权限并重试。
            </p>
            <button
              onClick={() => window.location.reload()}
              className="bg-amber-500/10 text-amber-400 border border-amber-500/20 px-6 py-2.5 rounded-xl font-medium hover:bg-amber-500/15 transition-colors"
            >
              重试
            </button>
          </div>
        </div>
      )}

      <ConnectionStatusOverlay
        state={connectionState}
        metadata={connectionMetadata}
        onReconnect={manualReconnect}
      />

      <main className="flex-1 relative overflow-hidden">
        <AnimatePresence mode="wait">
          {mode === 'voice' ? (
            <VoiceMode
              isAssistantTyping={isAssistantTyping}
              isUserSpeaking={isUserSpeaking}
              isMuted={isMuted}
              onMicClick={toggleMute}
              onStopSpeaking={stopSpeaking}
              isSpeaking={isSpeaking}
              statusText={statusText}
              calibrationState={calibrationState}
              getAnalyserNode={getAnalyserNode}
              conversationState={conversationState}
            />
          ) : (
            <ChatMode
              messages={steps}
              isAssistantTyping={isAssistantTyping}
              isSpeaking={isSpeaking}
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
