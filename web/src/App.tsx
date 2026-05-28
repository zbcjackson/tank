import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useAssistant } from './hooks/useAssistant';
import { useChannelNotifications } from './hooks/useChannelNotifications';
import { useConversationList } from './hooks/useConversationList';
import { VoiceMode } from './components/Assistant/VoiceMode';
import { ChatMode } from './components/Assistant/ChatMode';
import { ModeToggle } from './components/Assistant/ModeToggle';
import { ConnectionStatusOverlay } from './components/Assistant/ConnectionStatusOverlay';
import { ConversationList } from './components/Assistant/ConversationList';
import { ChannelAudioIndicator } from './components/Assistant/ChannelAudioIndicator';
import { ServerSettingsPanel } from './components/Assistant/ServerSettings';
import { useServerSettings } from './hooks/useServerSettings';
import * as api from './services/api';
import { AnimatePresence } from 'framer-motion';
import { Menu, Settings } from 'lucide-react';
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
  const server = useServerSettings();
  const [showSettings, setShowSettings] = useState(false);
  const wakeWordDetector = useWakeWordDetector();
  const [conversationListOpen, setConversationListOpen] = useState(false);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [activeChannelSlug, setActiveChannelSlug] = useState<string | null>(null);

  // Ref to break circular dependency: useAssistant needs the handler,
  // but useChannelNotifications needs appendSteps from useAssistant.
  const channelNotificationHandlerRef = useRef<((msg: import('./services/websocket').WebsocketMessage) => void) | null>(null);

  // Show server settings when not configured
  if (!server.isConfigured || showSettings) {
    return (
      <div style={APP_BG_STYLE}>
        <div data-tauri-drag-region className="tauri-drag-region fixed top-0 left-0 right-0 h-[36px]" style={{ zIndex: 20 }} />
        <ServerSettingsPanel
          isProbing={server.isProbing}
          probeError={server.probeError}
          currentHostPort={server.apiBaseUrl ? server.apiBaseUrl.replace(/^https:\/\//, '') : ''}
          onSave={async (hostPort) => {
            const ok = await server.saveSettings(hostPort);
            if (ok) setShowSettings(false);
            return ok;
          }}
          onClose={showSettings ? () => setShowSettings(false) : undefined}
        />
      </div>
    );
  }

  return (
    <AppWithServer
      server={server}
      wakeWordDetector={wakeWordDetector}
      setShowSettings={setShowSettings}
      conversationListOpen={conversationListOpen}
      setConversationListOpen={setConversationListOpen}
      activeConversationId={activeConversationId}
      setActiveConversationId={setActiveConversationId}
      activeChannelSlug={activeChannelSlug}
      setActiveChannelSlug={setActiveChannelSlug}
      channelNotificationHandlerRef={channelNotificationHandlerRef}
    />
  );
}

/** Inner component rendered only when server is configured. */
function AppWithServer({
  server,
  wakeWordDetector,
  setShowSettings,
  conversationListOpen,
  setConversationListOpen,
  activeConversationId,
  setActiveConversationId,
  activeChannelSlug,
  setActiveChannelSlug,
  channelNotificationHandlerRef,
}: {
  server: ReturnType<typeof useServerSettings>;
  wakeWordDetector: WakeWordDetector | null;
  setShowSettings: (v: boolean) => void;
  conversationListOpen: boolean;
  setConversationListOpen: (v: boolean) => void;
  activeConversationId: string | null;
  setActiveConversationId: (v: string | null) => void;
  activeChannelSlug: string | null;
  setActiveChannelSlug: (v: string | null) => void;
  channelNotificationHandlerRef: React.RefObject<((msg: import('./services/websocket').WebsocketMessage) => void) | null>;
}) {
  const backendUrl = server.wsBaseUrl || undefined;

  const conversationList = useConversationList();
  const conversationListRef = useRef(conversationList);
  conversationListRef.current = conversationList;

  const handleConversationMetadata = useCallback(
    (msg: import('./services/websocket').WebsocketMessage) => {
      const md = msg.metadata || {};
      const conversationId = md.conversation_id;
      if (typeof conversationId !== 'string' || !conversationId) return;
      const patch: { title?: string | null } = {};
      if ('title' in md) {
        const t = md.title;
        patch.title = typeof t === 'string' ? t : null;
      }
      conversationListRef.current.applyMetadataUpdate(conversationId, patch);
    },
    [],
  );

  const {
    steps,
    mode,
    assistantStatus,
    connectionState,
    connectionMetadata,
    sendMessage,
    respondToApproval,
    toggleMode,
    toggleContinuousMic,
    isContinuousMicOn,
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
    selectedUserId,
    setSelectedUserId,
    channelAudio,
    listenMode,
    setListenMode,
    voiceInterruptEnabled,
    setVoiceInterruptEnabled,
    chatSpeakEnabled,
    setChatSpeakEnabled,
    wakeWordAvailable,
    isPttActive,
    startPtt,
    stopPtt,
  } = useAssistant(SESSION_ID, wakeWordDetector, (msg) => {
    channelNotificationHandlerRef.current?.(msg);
  }, backendUrl, handleConversationMetadata);

  const channelNotifications = useChannelNotifications({
    activeChannelSlug,
    onActiveChannelMessages: appendSteps,
  });

  useEffect(() => {
    channelNotificationHandlerRef.current = channelNotifications.handleNotification;
  }, [channelNotifications.handleNotification, channelNotificationHandlerRef]);

  // Seed unread counts from API on mount
  useEffect(() => {
    api.channels.list()
      .then((channels) => channelNotifications.initFromChannels(channels))
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run on mount

  const handleSelectConversation = useCallback(
    async (conversationId: string) => {
      setConversationListOpen(false);
      setActiveConversationId(conversationId);
      await resumeConversation(conversationId);
    },
    [resumeConversation, setConversationListOpen, setActiveConversationId],
  );

  const handleNewConversation = useCallback(() => {
    setConversationListOpen(false);
    setActiveConversationId(null);
    setActiveChannelSlug(null);
    newConversation();
  }, [newConversation, setConversationListOpen, setActiveConversationId, setActiveChannelSlug]);

  const handleSelectChannel = useCallback(
    async (slug: string) => {
      setConversationListOpen(false);
      setActiveChannelSlug(slug);
      setActiveConversationId(null);
      try {
        const channel = await api.channels.get(slug);
        if (channel.conversation_id) {
          await resumeConversation(channel.conversation_id);
        }
        channelNotifications.markRead(slug);
      } catch {
        // Channel not found or fetch failed — ignore silently
      }
    },
    [resumeConversation, channelNotifications, setConversationListOpen, setActiveChannelSlug, setActiveConversationId],
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
      <div data-tauri-drag-region className="fixed top-0 left-0 right-0 h-[36px]" style={{ zIndex: 20 }} />
      <ConnectionStatusOverlay
        state={connectionState}
        metadata={connectionMetadata}
        onReconnect={manualReconnect}
        onChangeServer={() => setShowSettings(true)}
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
        conversations={conversationList.conversations}
        loading={conversationList.loading}
        refreshConversations={conversationList.refresh}
        applyConversationMetadata={conversationList.applyMetadataUpdate}
      />

      {/* Top-right buttons: settings gear + conversations menu */}
      <div className="absolute top-3 right-3 z-30 flex gap-1.5">
        <button
          onClick={() => setShowSettings(true)}
          className="p-2 rounded-lg bg-neutral-800/60 hover:bg-neutral-700/80 text-neutral-400 hover:text-neutral-200 transition-colors backdrop-blur-sm"
          title="Server Settings"
        >
          <Settings size={18} />
        </button>
        <button
          onClick={() => setConversationListOpen(true)}
          className="p-2 rounded-lg bg-neutral-800/60 hover:bg-neutral-700/80 text-neutral-400 hover:text-neutral-200 transition-colors backdrop-blur-sm"
          title="Conversations"
          data-testid="conversations-button"
        >
          <Menu size={18} />
        </button>
      </div>

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
              isContinuousMicOn={isContinuousMicOn}
              onToggleContinuousMic={toggleContinuousMic}
              onStopSpeaking={stopSpeaking}
              statusText={statusText}
              conversationState={conversationState}
              wakeWordKeyword={wakeWordKeyword}
              speaker={lastUserSpeaker}
              pauseAudioCapture={pauseAudioCapture}
              resumeAudioCapture={resumeAudioCapture}
              pendingApproval={pendingApproval}
              onApprovalRespond={respondToApproval}
              listenMode={listenMode}
              voiceInterruptEnabled={voiceInterruptEnabled}
              wakeWordAvailable={wakeWordAvailable}
              onListenModeChange={setListenMode}
              onVoiceInterruptEnabledChange={setVoiceInterruptEnabled}
              isPttActive={isPttActive}
              onPttStart={startPtt}
              onPttStop={stopPtt}
              steps={steps}
              sessionId={SESSION_ID}
              isSocketConnected={connectionState === 'connected'}
              hasSocketError={connectionState === 'failed'}
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
              sessionId={SESSION_ID}
              chatSpeakEnabled={chatSpeakEnabled}
              onChatSpeakEnabledChange={setChatSpeakEnabled}
              isPttActive={isPttActive}
              onPttStart={startPtt}
              onPttStop={stopPtt}
            />
          )}
        </AnimatePresence>
      </main>

      {capabilities.asr && <ModeToggle mode={mode} onToggle={toggleMode} />}
    </div>
  );
}

export default App;
