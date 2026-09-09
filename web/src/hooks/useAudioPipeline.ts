import { useState, useEffect, useRef } from 'react';

import {
  VoiceAssistantClient,
  type ConnectionState,
  type ConnectionMetadata,
  type Capabilities,
} from '../services/websocket';
import type { WebsocketMessage } from '../services/websocket';
import { AudioProcessor } from '../services/audio';
import { encodeAudioFrame } from '../services/audioFrame';
import { AudioPlayback } from '../services/audioPlayback';
import {
  OPUS_DECODE_SAMPLE_RATE,
  OpusDownlink,
  OpusUplink,
  float32ToInt16,
  isOpusSupported,
} from '../services/opusCodec';
import { createPlatformAudio } from '../services/platformAudio';
import type { StatusEvent } from './useAssistantStatus';
import type { ConversationState } from './useConversationSession';

interface UseAudioPipelineArgs {
  sessionId: string;
  capabilities: Capabilities;
  /** Pipeline wire rate declared by the backend in the "ready" signal. */
  pipelineSampleRate: number;
  conversationStateRef: React.RefObject<ConversationState>;
  onMessage: (msg: WebsocketMessage) => void;
  onBinaryMessage?: (data: ArrayBuffer) => void;
  dispatchStatus: (event: StatusEvent) => void;
  /**
   * When false, incoming TTS audio frames are dropped and any in-flight
   * playback is stopped. The WebSocket and ASR pipeline keep running so
   * the user can still see streamed text.
   */
  speakEnabledRef: React.RefObject<boolean>;
  /** Protocol-aware WebSocket base URL (e.g. "wss://192.168.1.50:8000"). Undefined = use window.location.host. */
  backendUrl?: string;
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
  pipelineSampleRate,
  conversationStateRef,
  onMessage,
  onBinaryMessage,
  dispatchStatus,
  speakEnabledRef,
  backendUrl,
}: UseAudioPipelineArgs) {
  const [connectionState, setConnectionState] = useState<ConnectionState>('idle');
  const [connectionMetadata, setConnectionMetadata] = useState<ConnectionMetadata>({});
  const [audioReady, setAudioReady] = useState(false);
  const [ttsRms, setTtsRms] = useState(0);

  const clientRef = useRef<VoiceAssistantClient | null>(null);
  const audioProcessorRef = useRef<AudioProcessor | null>(null);
  const playbackRef = useRef<AudioPlayback | null>(null);
  const audioStartedRef = useRef(false);
  const adapterReadyRef = useRef<Promise<void> | null>(null);

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

    // Opus negotiation state (protocol plan P1-2). The codecs terminate
    // HERE: downlink packets are decoded and re-framed as 8-byte-header PCM
    // at 48 kHz, so every downstream consumer (channel audio, playback)
    // keeps seeing exactly the frames it saw on raw-PCM connections.
    let opus: { uplink: OpusUplink; downlink: OpusDownlink } | null = null;
    let opusDeclared = false;

    const routeBinary = (data: ArrayBuffer) => {
      if (!speakEnabledRef.current) return;
      if (onBinaryMessage) {
        onBinaryMessage(data);
      } else {
        playback.play(data);
      }
    };

    const activateOpus = () => {
      if (opus) return;
      const downlink = new OpusDownlink((samples) => {
        routeBinary(encodeAudioFrame(float32ToInt16(samples), OPUS_DECODE_SAMPLE_RATE, 1));
      });
      const uplink = new OpusUplink((packet) => clientRef.current?.sendBinary(packet));
      opus = { uplink, downlink };
      console.info('[opus] negotiated — binary audio switched to opus packets');
    };

    const maybeDeclareOpus = (msg: WebsocketMessage) => {
      if (opusDeclared) return;
      const features = msg.metadata?.protocol_features;
      if (!Array.isArray(features) || !features.includes('opus')) return;
      opusDeclared = true;
      isOpusSupported()
        .then((supported) => {
          if (supported) {
            clientRef.current?.sendMessage('signal', 'capabilities', {
              enable: ['opus'],
            });
          } else {
            console.info('[opus] WebCodecs opus unavailable — staying on raw PCM');
          }
        })
        .catch((e) => console.error('[opus] support probe failed:', e));
    };

    const onCapabilitiesAck = (msg: WebsocketMessage) => {
      const enabled = msg.metadata?.enabled;
      if (Array.isArray(enabled) && enabled.includes('opus')) {
        activateOpus();
      }
    };

    // Create WebSocket client (pure transport)
    const client = new VoiceAssistantClient(sessionId, backendUrl);
    clientRef.current = client;
    client.connect(
      (msg) => {
        // Opus negotiation (P1-2): declare after ready, activate on ack.
        if (msg.type === 'signal' && msg.content === 'ready') {
          maybeDeclareOpus(msg);
        } else if (msg.type === 'signal' && msg.content === 'capabilities') {
          onCapabilitiesAck(msg);
        }
        // Reset playback gate when a new response cycle begins
        if (msg.type === 'signal' && msg.content === 'processing_started') {
          playback.reset();
        }
        // Backend detected user speech — stop local playback so the
        // user isn't talking over stale audio still draining on the frontend.
        if (msg.type === 'signal' && msg.content === 'speech_detected') {
          playback.stop();
          dispatchStatus({ type: 'INTERRUPT' });
        }
        onMessage(msg);
      },
      (data) => {
        // Opus connection: packets decode → re-framed PCM → routeBinary.
        if (opus) {
          opus.downlink.decode(new Uint8Array(data));
          return;
        }
        routeBinary(data);
      }, // Binary frames → playback or channel audio
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
    const audioProcessor = new AudioProcessor((data) => {
      if (opus) {
        opus.uplink.push(data);
      } else {
        client.sendAudio(data);
      }
    });

    // Create platform audio adapter and wire it to both services
    let disposed = false;
    adapterReadyRef.current = createPlatformAudio((error) => {
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
      if (opus) {
        opus.uplink.dispose();
        opus.downlink.dispose();
      }
      client.disconnect();
      audioProcessor.stop();
      playback.dispose();
      clientRef.current = null;
      audioProcessorRef.current = null;
      playbackRef.current = null;
    };
  }, [sessionId, onMessage, onBinaryMessage, dispatchStatus, conversationStateRef, speakEnabledRef, backendUrl]);

  // Start AudioProcessor only after capabilities confirm ASR is enabled
  useEffect(() => {
    const processor = audioProcessorRef.current;
    if (!processor || audioStartedRef.current) return;
    if (!capabilities.asr) return;

    audioStartedRef.current = true;

    // Ensure platform adapter is wired before starting (avoids race where
    // capabilities arrive before createPlatformAudio resolves)
    const startPipeline = async () => {
      if (adapterReadyRef.current) {
        await adapterReadyRef.current;
      }
      await processor.start(pipelineSampleRate);

      // Declare the actual capture rate so the backend can resample to the
      // pipeline's wire rate. Browsers often ignore the requested rate and
      // capture at 32/48 kHz; only signal when it actually differs.
      const rate = processor.getSampleRate();
      if (rate && rate !== pipelineSampleRate) {
        clientRef.current?.sendMessage('signal', 'audio_format', {
          sample_rate: rate,
          channels: 1,
        });
      }

      setAudioReady(true);
    };

    startPipeline().catch((err) => {
      console.error('Failed to start audio processor:', err);
      // A dead microphone must NOT flip the connection state — the WebSocket
      // is alive and chat/text streaming still work. Blocking the UI here made
      // the app unusable in environments without an audio input device
      // (headless browsers, VMs); the metadata alone is only surfaced inside
      // the connection overlay, which no longer renders.
      setConnectionMetadata({ error: 'Microphone unavailable — text input only' });
    });
    // pipelineSampleRate is read from the closure at start time; the ready
    // signal that sets it always arrives before capabilities.asr flips true.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
