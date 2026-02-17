import { useAssistant } from './hooks/useAssistant';
import { VoiceMode } from './components/Assistant/VoiceMode';
import { ChatMode } from './components/Assistant/ChatMode';
import { ModeToggle } from './components/Assistant/ModeToggle';
import { AnimatePresence, motion } from 'framer-motion';

// Simple session ID generator
const SESSION_ID = Math.random().toString(36).substring(7);

function App() {
  const {
    messages,
    mode,
    isAssistantTyping,
    connectionStatus,
    sendMessage,
    toggleMode,
    clearMessages
  } = useAssistant(SESSION_ID);

  return (
    <div className="h-screen w-full flex flex-col font-sans overflow-hidden relative">
      {connectionStatus === 'error' && (
        <div className="absolute inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-md text-white p-8 text-center">
            <div className="max-w-md">
                <h2 className="text-2xl font-bold mb-2">连接错误</h2>
                <p className="text-slate-400 mb-6">无法启动麦克风或连接到服务器，请检查权限并重试。</p>
                <button onClick={() => window.location.reload()} className="bg-primary px-6 py-2 rounded-xl font-bold">重试</button>
            </div>
        </div>
      )}
      <main className="flex-1 relative overflow-hidden">
        <AnimatePresence mode="wait">
          {mode === 'voice' ? (
            <VoiceMode 
              isAssistantTyping={isAssistantTyping}
              onMicClick={() => {}} // Audio is auto-starting in hook
              statusText={connectionStatus === 'connected' ? undefined : `Status: ${connectionStatus}`}
            />
          ) : (
            <ChatMode 
              messages={messages}
              isAssistantTyping={isAssistantTyping}
              onSendMessage={sendMessage}
            />
          )}
        </AnimatePresence>
      </main>

      <ModeToggle mode={mode} onToggle={toggleMode} />
    </div>
  );
}

export default App;
