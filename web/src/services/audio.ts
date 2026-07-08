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

  // Actual capture sample rate. Browsers often ignore the requested 16 kHz
  // AudioContext rate and capture at the hardware rate (32/48 kHz). We read
  // it back after start() so the backend can resample to the pipeline's
  // required 16 kHz. null until start() runs.
  private capturedSampleRate: number | null = null;

  // VAD gate — utterance-level, controlled by MicVAD callbacks
  private vadOpen = false;
  private micVad: MicVAD | null = null;
  private preRollBuffer = new RingBuffer<Int16Array>(PRE_ROLL_FRAMES);
  private trailingSilenceTimer: ReturnType<typeof setTimeout> | null = null;

  // PTT state — when true, MicVAD callbacks must not close vadOpen
  private pttActive = false;

  // When true, frontend MicVAD gating is disabled and all captured audio
  // flows to the backend (subject only to gateSpeech). The backend's VAD
  // becomes the sole utterance-boundary detector. Used in continuous mode
  // so the backend segmenter sees silence frames and can detect endpoints.
  private bypassMicVad = false;

  // Fired after MicVAD detects end of utterance and the trailing-silence
  // timer closes the gate. Used by wake-word mode to send end_of_utterance
  // and re-arm the detector.
  private onUtteranceEnd: (() => void) | null = null;

  // Wake word state
  private wakeWordDetector: WakeWordDetector | null = null;

  // Platform audio adapter (set externally via setPlatformAdapter)
  private platformAdapter: PlatformAudioAdapter | null = null;
  private captureHandle: CaptureHandle | null = null;

  // Set in stop(); checked after each await in start()/initVad() so a
  // mid-flight teardown (e.g. React StrictMode double-mount) cannot leak
  // a MicVAD instance that finishes loading after stop() returns.
  private disposed = false;

  constructor(onAudio: (data: Int16Array) => void) {
    this.onAudio = onAudio;
  }

  setPlatformAdapter(adapter: PlatformAudioAdapter) {
    this.platformAdapter = adapter;
  }

  async start(targetSampleRate = 16000) {
    // If a platform adapter with native capture exists (e.g. Tauri), use its
    // capture pipeline — no browser getUserMedia/AudioWorklet/VAD needed.
    // BrowserAudioAdapter does NOT handle capture (handlesCapture=false), so
    // we fall through to the AudioWorklet path below.
    if (this.platformAdapter?.handlesCapture) {
      this.captureHandle = await this.platformAdapter.startCapture((samples: Int16Array) => {
        if (!this.gateSpeech) {
          this.onAudio(samples);
        }
      });
      if (this.disposed) {
        this.captureHandle.stop();
        this.captureHandle = null;
        return;
      }
      // IMPORTANT: Start with mic GATED. The useAssistant hook will
      // explicitly resume() when user enables audio via PTT or toggle.
      this.gateSpeech = true;
      return;
    }

    // Browser mode — getUserMedia + AudioWorklet
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error(
        'Microphone access requires HTTPS or localhost. ' +
          'Ensure the page is served over a secure context.',
      );
    }
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: 16000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
    if (this.disposed) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
      return;
    }

    this.audioContext = new (
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    )({
      sampleRate: targetSampleRate,
    });

    // Read back the actual rate the browser gave us — it may differ from the
    // requested rate (common on Linux where hardware rates are fixed).
    this.capturedSampleRate = this.audioContext.sampleRate;

    await this.audioContext.audioWorklet.addModule('/audio-processor.js');
    if (this.disposed) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
      this.audioContext.close();
      this.audioContext = null;
      return;
    }

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
    if (this.disposed) return;

    // IMPORTANT: Start with mic GATED (gateSpeech=true). The useAssistant
    // hook will explicitly resume() when the user has taken action to
    // enable audio (PTT press, continuous toggle, wake word detection).
    // This prevents audio from flowing on page load or HMR before the
    // orchestration effect can pause the processor.
    if (!this.wakeWordDetector) {
      this.gateSpeech = true;
      this.micVad?.start();
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

    if (!this.gateSpeech && (this.bypassMicVad || this.vadOpen)) {
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

      const newVad = await MicVADClass.new({
        model: 'v5',
        baseAssetPath: '/vad/',
        onnxWASMBasePath: '/ort/',
        startOnLoad: false,

        // Share our existing MediaStream — no second mic
        getStream: () => Promise.resolve(capturedStream),
        // No-ops: we manage the stream lifecycle ourselves
        pauseStream: () => Promise.resolve(),
        resumeStream: () => Promise.resolve(capturedStream),

        onSpeechStart: () => {
          if (this.bypassMicVad || this.gateSpeech) return;
          console.log('[AudioProcessor] VAD: speech start');
          // Cancel any pending trailing-silence close — user is speaking again
          if (this.trailingSilenceTimer) {
            clearTimeout(this.trailingSilenceTimer);
            this.trailingSilenceTimer = null;
          }
          this.vadOpen = true;
          // Flush pre-roll buffer so backend gets the beginning of the utterance
          for (const frame of this.preRollBuffer.drain()) {
            this.onAudio(frame);
          }
        },

        onSpeechEnd: () => {
          if (this.pttActive || this.bypassMicVad || this.gateSpeech) return;
          console.log('[AudioProcessor] VAD: speech end, sending trailing silence');
          this.trailingSilenceTimer = setTimeout(() => {
            this.trailingSilenceTimer = null;
            this.vadOpen = false;
            this.preRollBuffer.clear();
            console.log('[AudioProcessor] VAD: trailing silence done, gate closed');
            this.onUtteranceEnd?.();
          }, TRAILING_SILENCE_MS);
        },

        onVADMisfire: () => {
          if (this.pttActive || this.bypassMicVad || this.gateSpeech) return;
          console.log('[AudioProcessor] VAD: misfire');
          this.vadOpen = false;
        },
      });

      // If stop() ran while MicVAD was loading, discard it so it never starts.
      if (this.disposed) {
        newVad.destroy();
        return;
      }
      this.micVad = newVad;
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
      // Only restart MicVAD if the session gate is open — in wake-word
      // mode (gateSpeech=true), enableWakeWord owns MicVAD lifecycle.
      if (!this.gateSpeech) {
        this.micVad.start();
      }
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
   * Returns the actual capture sample rate after start(), or null if not yet
   * started. Browsers may ignore the requested 16 kHz and capture at the
   * hardware rate (32/48 kHz). The backend uses this to resample correctly.
   */
  getSampleRate(): number | null {
    return this.capturedSampleRate;
  }

  /**
   * In bypass mode the frontend MicVAD no longer gates audio — all captured
   * frames flow to the backend (subject only to `gateSpeech`). Used by
   * continuous mode so the backend segmenter sees silence frames and can
   * detect utterance endpoints itself. MicVAD is paused while bypassed to
   * avoid spurious callbacks and CPU cost.
   */
  setBypassMicVad(bypass: boolean): void {
    if (this.bypassMicVad === bypass) return;
    this.bypassMicVad = bypass;
    this.clearTrailingSilenceTimer();
    if (bypass) {
      this.vadOpen = true;
      this.micVad?.pause();
    } else {
      this.vadOpen = false;
      this.preRollBuffer.clear();
      if (!this.gateSpeech) {
        this.micVad?.start();
      }
    }
  }

  /**
   * Subscribe to end-of-utterance: fires after MicVAD detects speech end
   * and the trailing-silence timer closes the gate. Wake-word mode uses
   * this to send `end_of_utterance` and re-arm the detector.
   */
  setOnUtteranceEnd(callback: (() => void) | null) {
    this.onUtteranceEnd = callback;
  }

  /**
   * Enable wake word detection. Gates audio (stops forwarding to backend).
   * The detector manages its own audio pipeline via WebVoiceProcessor.
   * NOTE: Two mic streams will be active simultaneously (our worklet + WebVoiceProcessor).
   */
  async enableWakeWord(detector: WakeWordDetector, onDetected: () => void): Promise<void> {
    // Wake word engines (OpenWakeWord, Porcupine) manage their own mic capture
    // via getUserMedia, which doesn't exist in Tauri's WKWebView. Skip in
    // Tauri — native audio capture is handled by the platform adapter instead.
    if (this.platformAdapter?.handlesCapture) {
      console.info('[AudioProcessor] Wake word skipped — platform adapter active (native capture)');
      return;
    }
    console.log('[AudioProcessor] Enabling wake word detection, gating audio');
    this.wakeWordDetector = detector;
    this.gateSpeech = true;
    this.vadOpen = false;
    this.clearTrailingSilenceTimer();
    if (this.micVad) {
      await this.micVad.pause();
    }
    await detector.start(onDetected);
  }

  /**
   * Disable wake word detection. Ungates audio so it flows to the backend.
   * Does NOT call detector.stop() — the startSession guard prevents
   * double-activation, and enableWakeWord is the authoritative re-arm point.
   */
  async disableWakeWord(): Promise<void> {
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

  /**
   * Open both gates unconditionally and flush the pre-roll buffer.
   * Used by push-to-talk so audio flows immediately without waiting
   * for frontend MicVAD to detect speech start.
   */
  resumeForPtt() {
    this.pttActive = true;
    this.gateSpeech = false;
    this.vadOpen = true;
    this.clearTrailingSilenceTimer();
    for (const frame of this.preRollBuffer.drain()) {
      this.onAudio(frame);
    }
    this.micVad?.start();
  }

  /**
   * Close both gates for push-to-talk release.
   * Does NOT pause MicVAD — let it keep running so it's ready
   * for the next PTT press without re-initialization latency.
   */
  pauseForPtt() {
    this.pttActive = false;
    this.gateSpeech = true;
    this.vadOpen = false;
    this.clearTrailingSilenceTimer();
  }

  stop() {
    this.disposed = true;
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
