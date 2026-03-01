import { useAssistant } from './hooks/useAssistant';
import { VoiceMode } from './components/Assistant/VoiceMode';
import { ChatMode } from './components/Assistant/ChatMode';
import { ModeToggle } from './components/Assistant/ModeToggle';
import { ConnectionStatusOverlay } from './components/Assistant/ConnectionStatusOverlay';
import { AnimatePresence } from 'framer-motion';

// Simple session ID generator
const SESSION_ID = Math.random().toString(36).substring(7);

function App() {
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
  } = useAssistant(SESSION_ID);

  const calibrationStatusText =
    calibrationState.status === 'calibrating'
      ? '正在校准背景噪声...'
      : calibrationState.status === 'error'
        ? '噪声校准失败，使用默认阈值'
        : undefined;
  const statusText =
    calibrationStatusText ||
    (connectionState === 'connected' ? undefined : `Status: ${connectionState}`);

  return (
    <div className="h-screen w-full flex flex-col font-sans overflow-hidden relative">
      {connectionState === 'failed' && calibrationState.status === 'error' && (
        <div className="absolute inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-md text-white p-8 text-center">
          <div className="max-w-md">
            <h2 className="text-2xl font-bold mb-2">连接错误</h2>
            <p className="text-slate-400 mb-6">无法启动麦克风或连接到服务器，请检查权限并重试。</p>
            <button
              onClick={() => window.location.reload()}
              className="bg-primary px-6 py-2 rounded-xl font-bold"
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
            />
          ) : (
            <ChatMode
              messages={steps}
              isAssistantTyping={isAssistantTyping}
              isSpeaking={isSpeaking}
              onSendMessage={sendMessage}
              onStopSpeaking={stopSpeaking}
            />
          )}
        </AnimatePresence>
      </main>

      <ModeToggle mode={mode} onToggle={toggleMode} />
    </div>
  );
}

export default App;
