import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useAssistant } from './hooks/useAssistant';
import { useChannelNotifications } from './hooks/useChannelNotifications';
import { VoiceMode } from './components/Assistant/VoiceMode';
import { ChatMode } from './components/Assistant/ChatMode';
import { ModeToggle } from './components/Assistant/ModeToggle';
import { ConnectionStatusOverlay } from './components/Assistant/ConnectionStatusOverlay';
import { ConversationList } from './components/Assistant/ConversationList';
import { ChannelAudioIndicator } from './components/Assistant/ChannelAudioIndicator';
import { AnimatePresence } from 'framer-motion';
import { Menu } from 'lucide-react';
import type { WakeWordDetector } from './services/wakeWordDetector';
import { createWakeWordDetector, type WakeWordEngine } from './services/wakeWordFactory';
import type { ApprovalContent } from './types/message';

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
  const [conversationListOpen, setConversationListOpen] = useState(false);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [activeChannelSlug, setActiveChannelSlug] = useState<string | null>(null);

  // Ref to break circular dependency: useAssistant needs the handler,
  // but useChannelNotifications needs appendSteps from useAssistant.
  const channelNotificationHandlerRef = useRef<((msg: import('./services/websocket').WebsocketMessage) => void) | null>(null);

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
    resumeConversation,
    newConversation,
    appendSteps,
    capabilities,
    conversationState,
    wakeWordKeyword,
    ttsRms,
    selectedUserId,
    setSelectedUserId,
    channelAudio,
  } = useAssistant(SESSION_ID, wakeWordDetector, (msg) => {
    channelNotificationHandlerRef.current?.(msg);
  });

  const channelNotifications = useChannelNotifications({
    activeChannelSlug,
    onActiveChannelMessages: appendSteps,
  });

  useEffect(() => {
    channelNotificationHandlerRef.current = channelNotifications.handleNotification;
  }, [channelNotifications.handleNotification]);

  // Seed unread counts from API on mount
  useEffect(() => {
    fetch('/api/channels')
      .then((r) => (r.ok ? r.json() : []))
      .then((channels) => channelNotifications.initFromChannels(channels))
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSelectConversation = useCallback(
    async (conversationId: string) => {
      setConversationListOpen(false);
      setActiveConversationId(conversationId);
      await resumeConversation(conversationId);
    },
    [resumeConversation],
  );

  const handleNewConversation = useCallback(() => {
    setConversationListOpen(false);
    setActiveConversationId(null);
    setActiveChannelSlug(null);
    newConversation();
  }, [newConversation]);

  const handleSelectChannel = useCallback(
    async (slug: string) => {
      setConversationListOpen(false);
      setActiveChannelSlug(slug);
      setActiveConversationId(null);
      try {
        const resp = await fetch(`/api/channels/${slug}`);
        if (!resp.ok) return;
        const channel = await resp.json();
        if (channel.conversation_id) {
          await resumeConversation(channel.conversation_id);
        }
        channelNotifications.markRead(slug);
      } catch {
        // Channel not found or fetch failed — ignore silently
      }
    },
    [resumeConversation, channelNotifications],
  );

  const lastUserSpeaker = useMemo(() => {
    for (let i = steps.length - 1; i >= 0; i--) {
      if (steps[i].role === 'user') return steps[i].speaker;
    }
    return undefined;
  }, [steps]);

  const pendingApproval = useMemo(() => {
    for (let i = steps.length - 1; i >= 0; i--) {
      if (steps[i].type === 'approval') {
        const content = steps[i].content as ApprovalContent;
        if (content.status === 'pending') {
          return content;
        }
      }
    }
    return null;
  }, [steps]);

  const statusText = connectionState === 'connected' ? undefined : `Status: ${connectionState}`;

  return (
    <div className="h-screen w-full flex flex-col overflow-hidden relative" style={APP_BG_STYLE}>
      <ConnectionStatusOverlay
        state={connectionState}
        metadata={connectionMetadata}
        onReconnect={manualReconnect}
      />

      {/* Conversation list sidebar */}
      <ConversationList
        open={conversationListOpen}
        onClose={() => setConversationListOpen(false)}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        activeConversationId={activeConversationId}
        onSelectChannel={handleSelectChannel}
        activeChannelSlug={activeChannelSlug}
        unreadCounts={channelNotifications.unreadCounts}
        subscribedChannels={channelAudio.subscribedChannels}
        onToggleChannelSubscription={channelAudio.toggleSubscription}
      />

      {/* Conversation list toggle button */}
      <button
        onClick={() => setConversationListOpen(true)}
        className="absolute top-3 right-3 z-30 p-2 rounded-lg bg-neutral-800/60 hover:bg-neutral-700/80 text-neutral-400 hover:text-neutral-200 transition-colors backdrop-blur-sm"
        title="Conversations"
        data-testid="conversations-button"
      >
        <Menu size={18} />
      </button>

      {/* Channel audio playback indicator + stop button */}
      <ChannelAudioIndicator
        slug={channelAudio.channelAudioSlug}
        onStop={channelAudio.stopChannelAudio}
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
              wakeWordKeyword={wakeWordKeyword}
              ttsRms={ttsRms}
              speaker={lastUserSpeaker}
              pauseAudioCapture={pauseAudioCapture}
              resumeAudioCapture={resumeAudioCapture}
              pendingApproval={pendingApproval}
              onApprovalRespond={respondToApproval}
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
              selectedUserId={selectedUserId}
              onSelectUser={setSelectedUserId}
            />
          )}
        </AnimatePresence>
      </main>

      {capabilities.asr && <ModeToggle mode={mode} onToggle={toggleMode} />}
    </div>
  );
}

export default App;
