import { useState, useEffect, useRef } from 'react';

import {
  VoiceAssistantClient,
  type ConnectionState,
  type ConnectionMetadata,
  type Capabilities,
} from '../services/websocket';
import type { WebsocketMessage } from '../services/websocket';
import { AudioProcessor } from '../services/audio';
import { AudioPlayback } from '../services/audioPlayback';
import { createPlatformAudio } from '../services/platformAudio';
import type { StatusEvent } from './useAssistantStatus';
import type { ConversationState } from './useConversationSession';

interface UseAudioPipelineArgs {
  sessionId: string;
  capabilities: Capabilities;
  conversationStateRef: React.RefObject<ConversationState>;
  onMessage: (msg: WebsocketMessage) => void;
  dispatchStatus: (event: StatusEvent) => void;
}

/**
 * Manages the audio pipeline lifecycle: WebSocket client, AudioProcessor,
 * AudioPlayback, and platform audio adapter.
 *
 * Separated from useAssistant so the setup/teardown/event-listener wiring
 * can be reasoned about independently of message parsing and UI state.
 */
export function useAudioPipeline({
  sessionId,
  capabilities,
  conversationStateRef,
  onMessage,
  dispatchStatus,
}: UseAudioPipelineArgs) {
  const [connectionState, setConnectionState] = useState<ConnectionState>('idle');
  const [connectionMetadata, setConnectionMetadata] = useState<ConnectionMetadata>({});
  const [audioReady, setAudioReady] = useState(false);
  const [ttsRms, setTtsRms] = useState(0);

  const clientRef = useRef<VoiceAssistantClient | null>(null);
  const audioProcessorRef = useRef<AudioProcessor | null>(null);
  const playbackRef = useRef<AudioPlayback | null>(null);
  const audioStartedRef = useRef(false);

  // Main lifecycle: create and wire up all audio services
  useEffect(() => {
    // Create AudioPlayback coordinator
    const playback = new AudioPlayback();
    playbackRef.current = playback;
    playback.setOnSpeakingChange((speaking) => {
      if (speaking) {
        dispatchStatus({ type: 'AUDIO_CHUNK' });
      } else {
        dispatchStatus({ type: 'SPEAKING_ENDED' });
      }
    });

    // Create WebSocket client (pure transport)
    const client = new VoiceAssistantClient(sessionId);
    clientRef.current = client;
    client.connect(
      onMessage,
      (data) => playback.play(data), // Binary frames → playback
      () => {}, // onOpen - handled by onConnectionStateChange
      (state, metadata) => {
        setConnectionState(state);
        setConnectionMetadata(metadata || {});

        // Reset UI state on reconnecting
        if (state === 'reconnecting') {
          dispatchStatus({ type: 'RESET' });
        }
      },
    );

    // AudioProcessor is created eagerly but started lazily (after capabilities arrive)
    const audioProcessor = new AudioProcessor((data) => client.sendAudio(data));

    // Create platform audio adapter and wire it to both services
    let disposed = false;
    createPlatformAudio((error) => {
      console.error('[useAudioPipeline] Platform audio error:', error);
    }).then((adapter) => {
      if (disposed) {
        adapter.dispose();
        return;
      }
      adapter.setOnRmsChange((rms) => setTtsRms(rms));
      audioProcessor.setPlatformAdapter(adapter);
      playback.setPlatformAdapter(adapter);
    });

    audioProcessorRef.current = audioProcessor;
    audioStartedRef.current = false;

    const handleBeforeUnload = () => {
      clientRef.current?.disconnect();
      audioProcessorRef.current?.stop();
      playbackRef.current?.dispose();
    };
    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      disposed = true;
      window.removeEventListener('beforeunload', handleBeforeUnload);
      client.disconnect();
      audioProcessor.stop();
      playback.dispose();
      clientRef.current = null;
      audioProcessorRef.current = null;
      playbackRef.current = null;
    };
  }, [sessionId, onMessage, dispatchStatus, conversationStateRef]);

  // Start AudioProcessor only after capabilities confirm ASR is enabled
  useEffect(() => {
    const processor = audioProcessorRef.current;
    if (!processor || audioStartedRef.current) return;
    if (!capabilities.asr) return;

    audioStartedRef.current = true;
    processor
      .start()
      .then(() => {
        setAudioReady(true);
      })
      .catch((err) => {
        console.error('Failed to start audio processor:', err);
        setConnectionState('failed');
        setConnectionMetadata({ error: 'Failed to start audio processor' });
      });
  }, [capabilities.asr]);

  return {
    clientRef,
    audioProcessorRef,
    playbackRef,
    connectionState,
    connectionMetadata,
    audioReady,
    ttsRms,
  };
}
