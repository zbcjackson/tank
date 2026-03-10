import { useAssistant } from './hooks/useAssistant';
import { VoiceMode } from './components/Assistant/VoiceMode';
import { ChatMode } from './components/Assistant/ChatMode';
import { ModeToggle } from './components/Assistant/ModeToggle';
import { ConnectionStatusOverlay } from './components/Assistant/ConnectionStatusOverlay';
import { AnimatePresence } from 'framer-motion';

const SESSION_ID = Math.random().toString(36).substring(7);
const APP_BG_STYLE = { background: '#0a0a0a' };

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
    pauseAudioCapture,
    resumeAudioCapture,
    capabilities,
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
