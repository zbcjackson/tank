import { useState, useEffect, useRef } from 'react';

import {
  VoiceAssistantClient,
  type ConnectionState,
  type ConnectionMetadata,
  type Capabilities,
} from '../services/websocket';
import type { WebsocketMessage } from '../services/websocket';
import { AudioProcessor, type CalibrationState } from '../services/audio';
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
  const [isUserSpeaking, setIsUserSpeaking] = useState(false);
  const [calibrationState, setCalibrationState] = useState<CalibrationState>({ status: 'idle' });
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
          setIsUserSpeaking(false);
        }
      },
    );

    // AudioProcessor is created eagerly but started lazily (after capabilities arrive)
    const audioProcessor = new AudioProcessor((data) => client.sendAudio(data), {
      onSpeechChange: (isSpeech) => {
        setIsUserSpeaking(isSpeech);
        // Only dispatch listening status when conversation gate is open
        if (conversationStateRef.current === 'active') {
          dispatchStatus({ type: isSpeech ? 'USER_SPEECH_START' : 'USER_SPEECH_END' });
        }
      },
      onCalibrationChange: (state) => {
        setCalibrationState(state);
        if (state.status !== 'ready') setIsUserSpeaking(false);
      },
    });

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

    const handleDeviceChange = () => audioProcessorRef.current?.recalibrate();
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        audioProcessorRef.current?.recalibrate();
      }
    };
    navigator.mediaDevices?.addEventListener('devicechange', handleDeviceChange);
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      disposed = true;
      window.removeEventListener('beforeunload', handleBeforeUnload);
      navigator.mediaDevices?.removeEventListener('devicechange', handleDeviceChange);
      document.removeEventListener('visibilitychange', handleVisibility);
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
    isUserSpeaking,
    setIsUserSpeaking,
    calibrationState,
    audioReady,
    ttsRms,
  };
}
