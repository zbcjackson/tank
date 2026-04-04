import type { MicVAD } from '@ricky0123/vad-web';

import type { PlatformAudioAdapter, CaptureHandle } from './platformAudio';
import type { WakeWordDetector } from './wakeWordDetector';
import { RingBuffer } from './ringBuffer';

/** Number of pre-roll frames to buffer (~40ms at 20ms/frame). */
const PRE_ROLL_FRAMES = 5;

/**
 * After MicVAD fires onSpeechEnd, keep the audio gate open for this many ms
 * so the backend receives enough trailing silence to trigger its own endpoint
 * detection (backend min_silence_ms = 1000ms).
 */
const TRAILING_SILENCE_MS = 1200;

export class AudioProcessor {
  private audioContext: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private onAudio: (data: Int16Array) => void;
  private gateSpeech = true;
  private muted = false;

  // VAD gate — utterance-level, controlled by MicVAD callbacks
  private vadOpen = false;
  private micVad: MicVAD | null = null;
  private preRollBuffer = new RingBuffer<Int16Array>(PRE_ROLL_FRAMES);
  private trailingSilenceTimer: ReturnType<typeof setTimeout> | null = null;

  // Wake word state
  private wakeWordDetector: WakeWordDetector | null = null;

  // Platform audio adapter (set externally via setPlatformAdapter)
  private platformAdapter: PlatformAudioAdapter | null = null;
  private captureHandle: CaptureHandle | null = null;

  constructor(onAudio: (data: Int16Array) => void) {
    this.onAudio = onAudio;
  }

  setPlatformAdapter(adapter: PlatformAudioAdapter) {
    this.platformAdapter = adapter;
  }

  async start() {
    // If a platform adapter exists (e.g. Tauri), use its capture — no VAD
    if (this.platformAdapter) {
      this.captureHandle = await this.platformAdapter.startCapture((samples: Int16Array) => {
        if (!this.gateSpeech) {
          this.onAudio(samples);
        }
      });
      this.gateSpeech = false;
      return;
    }

    // Browser mode — getUserMedia + AudioWorklet
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: 16000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });

    this.audioContext = new (
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    )({
      sampleRate: 16000,
    });

    await this.audioContext.audioWorklet.addModule('/audio-processor.js');

    this.source = this.audioContext.createMediaStreamSource(this.stream);
    this.workletNode = new AudioWorkletNode(this.audioContext, 'audio-capture-processor');

    this.workletNode.port.onmessage = (event: MessageEvent) => {
      if (event.data instanceof ArrayBuffer) {
        const int16Array = new Int16Array(event.data);
        this.handleCapturedFrame(int16Array);
      }
    };

    this.source.connect(this.workletNode);
    this.workletNode.connect(this.audioContext.destination);

    // Initialize MicVAD for utterance-level gating
    await this.initVad();

    // No calibration needed — backend SileroVAD handles segmentation
    if (!this.wakeWordDetector) {
      this.gateSpeech = false;
    }
  }

  /**
   * Route a captured audio frame through the dual-gate logic.
   * Always pushes to the pre-roll buffer. Only forwards to onAudio
   * when both gates allow (session gate open AND VAD detected speech).
   */
  private handleCapturedFrame(frame: Int16Array): void {
    // Always buffer for pre-roll regardless of gate state
    this.preRollBuffer.push(frame);

    if (!this.gateSpeech && this.vadOpen) {
      this.onAudio(frame);
    }
  }

  /**
   * Initialize MicVAD using the existing MediaStream.
   * Falls back gracefully — if init fails, vadOpen stays true (always-open gate).
   */
  private async initVad(): Promise<void> {
    if (!this.stream) return;

    const capturedStream = this.stream;

    try {
      const { MicVAD: MicVADClass } = await import('@ricky0123/vad-web');

      this.micVad = await MicVADClass.new({
        model: 'v5',
        baseAssetPath: '/vad/',
        onnxWASMBasePath: '/ort/',
        startOnLoad: true,

        // Share our existing MediaStream — no second mic
        getStream: () => Promise.resolve(capturedStream),
        // No-ops: we manage the stream lifecycle ourselves
        pauseStream: () => Promise.resolve(),
        resumeStream: () => Promise.resolve(capturedStream),

        onSpeechStart: () => {
          console.log('[AudioProcessor] VAD: speech start');
          // Cancel any pending trailing-silence close — user is speaking again
          if (this.trailingSilenceTimer) {
            clearTimeout(this.trailingSilenceTimer);
            this.trailingSilenceTimer = null;
          }
          this.vadOpen = true;
          // Flush pre-roll buffer so backend gets the beginning of the utterance
          if (!this.gateSpeech) {
            for (const frame of this.preRollBuffer.drain()) {
              this.onAudio(frame);
            }
          } else {
            this.preRollBuffer.clear();
          }
        },

        onSpeechEnd: () => {
          console.log('[AudioProcessor] VAD: speech end, sending trailing silence');
          // Keep gate open so the AudioWorklet continues forwarding silence
          // frames to the backend. The backend needs ~1s of silence to trigger
          // its own END_SPEECH endpoint detection.
          this.trailingSilenceTimer = setTimeout(() => {
            this.trailingSilenceTimer = null;
            this.vadOpen = false;
            this.preRollBuffer.clear();
            console.log('[AudioProcessor] VAD: trailing silence done, gate closed');
          }, TRAILING_SILENCE_MS);
        },

        onVADMisfire: () => {
          console.log('[AudioProcessor] VAD: misfire');
          this.vadOpen = false;
        },
      });
    } catch (err) {
      // Graceful fallback — VAD gate stays always-open
      console.warn('[AudioProcessor] MicVAD init failed, falling back to no VAD gating:', err);
      this.vadOpen = true;
      this.micVad = null;
    }
  }

  /**
   * During TTS playback, bypass the frontend VAD gate so all audio
   * flows to the backend. The backend VAD (with its echo-guard threshold)
   * handles speech detection and can trigger an interrupt.
   *
   * When playback ends, resume MicVAD but keep the gate open so any
   * in-progress speech continues flowing. MicVAD's onSpeechEnd will
   * close the gate naturally when the user stops talking.
   */
  setSpeaking(speaking: boolean): void {
    if (!this.micVad) return;

    if (speaking) {
      this.clearTrailingSilenceTimer();
      // Pause MicVAD (its echo-unaware model would misfire) but keep
      // the gate open so captured frames still reach the backend.
      this.micVad.pause();
      this.vadOpen = true;
    } else {
      // Resume MicVAD but do NOT close vadOpen — if the user is
      // mid-sentence the gate must stay open until MicVAD fires
      // onSpeechEnd naturally.
      this.micVad.start();
    }
  }

  setMuted(muted: boolean) {
    this.muted = muted;
    this.stream?.getAudioTracks().forEach((track) => {
      track.enabled = !muted;
    });
  }

  isMuted(): boolean {
    return this.muted;
  }

  /**
   * Enable wake word detection. Gates audio (stops forwarding to backend).
   * The detector manages its own audio pipeline via WebVoiceProcessor.
   * NOTE: Two mic streams will be active simultaneously (our worklet + WebVoiceProcessor).
   */
  async enableWakeWord(detector: WakeWordDetector, onDetected: () => void): Promise<void> {
    console.log('[AudioProcessor] Enabling wake word detection, gating audio');
    this.wakeWordDetector = detector;
    this.gateSpeech = true;
    this.micVad?.pause();
    await detector.start(onDetected);
  }

  /**
   * Disable wake word detection. Ungates audio so it flows to the backend.
   */
  async disableWakeWord(): Promise<void> {
    if (this.wakeWordDetector) {
      await this.wakeWordDetector.stop();
    }
    this.wakeWordDetector = null;
    this.gateSpeech = false;
    this.micVad?.start();
  }

  private clearTrailingSilenceTimer(): void {
    if (this.trailingSilenceTimer) {
      clearTimeout(this.trailingSilenceTimer);
      this.trailingSilenceTimer = null;
    }
  }

  pause() {
    this.clearTrailingSilenceTimer();
    this.gateSpeech = true;
    this.micVad?.pause();
  }

  resume() {
    this.gateSpeech = false;
    this.micVad?.start();
  }

  stop() {
    this.clearTrailingSilenceTimer();
    this.wakeWordDetector?.release();
    this.wakeWordDetector = null;

    this.micVad?.destroy();
    this.micVad = null;

    if (this.captureHandle) {
      this.captureHandle.stop();
      this.captureHandle = null;
      return;
    }

    this.source?.disconnect();
    this.workletNode?.disconnect();
    this.workletNode?.port.close();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.audioContext?.close();
  }
}
