import type { PlatformAudioAdapter, CaptureHandle } from './platformAudio';
import type { WakeWordDetector } from './wakeWordDetector';

export class AudioProcessor {
  private audioContext: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private onAudio: (data: Int16Array) => void;
  private gateSpeech = true;
  private muted = false;

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
    // If a platform adapter exists (e.g. Tauri), use its capture
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
        if (!this.gateSpeech) {
          const int16Array = new Int16Array(event.data);
          this.onAudio(int16Array);
        }
      }
    };

    this.source.connect(this.workletNode);
    this.workletNode.connect(this.audioContext.destination);

    // No calibration needed — backend SileroVAD handles segmentation
    if (!this.wakeWordDetector) {
      this.gateSpeech = false;
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
  }

  pause() {
    this.gateSpeech = true;
  }

  resume() {
    this.gateSpeech = false;
  }

  stop() {
    this.wakeWordDetector?.release();
    this.wakeWordDetector = null;

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
