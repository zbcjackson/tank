import type { WakeWordDetector } from './wakeWordDetector';

export interface VADConfig {
  threshold: number;
  preRollSize: number; // frames (128 samples each at 16kHz)
  hangoverMax: number; // frames
}

export interface CalibrationConfig {
  durationMs: number;
  multiplier: number;
  minThreshold: number;
}

export type CalibrationStatus = 'idle' | 'calibrating' | 'ready' | 'error';

export interface CalibrationState {
  status: CalibrationStatus;
  threshold?: number;
  error?: string;
}

export function computeCalibrationThreshold(
  rmsSamples: number[],
  calibrationConfig: CalibrationConfig,
  fallbackThreshold: number,
) {
  if (!rmsSamples.length) {
    return { threshold: fallbackThreshold, usedFallback: true };
  }
  const sum = rmsSamples.reduce((acc, v) => acc + v, 0);
  const mean = sum / rmsSamples.length;
  const threshold = Math.max(mean * calibrationConfig.multiplier, calibrationConfig.minThreshold);
  return { threshold, usedFallback: false };
}

const DEFAULT_CALIBRATION_CONFIG: CalibrationConfig = {
  durationMs: 1000,
  multiplier: 3,
  minThreshold: 0.004,
};

export const DEFAULT_VAD_CONFIG: VADConfig = {
  threshold: 0.01,
  preRollSize: 25, // ~200ms
  hangoverMax: 188, // ~1500ms — enough silence for backend ASR endpoint detection
};

interface AudioProcessorOptions {
  onSpeechChange?: (isSpeech: boolean) => void;
  vadConfig?: Partial<VADConfig>;
  calibrationConfig?: Partial<CalibrationConfig>;
  onCalibrationChange?: (state: CalibrationState) => void;
}

export class AudioProcessor {
  private audioContext: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private onAudio: (data: Int16Array) => void;
  private onSpeechChange?: (isSpeech: boolean) => void;
  private vadConfig: VADConfig;
  private calibrationConfig: CalibrationConfig;
  private onCalibrationChange?: (state: CalibrationState) => void;
  private calibrationState: CalibrationState = { status: 'idle' };
  private gateSpeech = true;
  private rmsSamples: number[] = [];
  private calibrationToken: symbol | null = null;
  private muted = false;

  // Wake word state
  private wakeWordDetector: WakeWordDetector | null = null;
  private wakeWordBuffer: Int16Array[] = [];
  private wakeWordBufferedSamples = 0;
  private wakeWordCallback: (() => void) | null = null;
  private readonly MAX_WAKE_WORD_BUFFER_SAMPLES = 16000 * 5; // 5 seconds max

  constructor(onAudio: (data: Int16Array) => void, options?: AudioProcessorOptions) {
    this.onAudio = onAudio;
    this.onSpeechChange = options?.onSpeechChange;
    this.onCalibrationChange = options?.onCalibrationChange;
    this.vadConfig = { ...DEFAULT_VAD_CONFIG, ...options?.vadConfig };
    this.calibrationConfig = { ...DEFAULT_CALIBRATION_CONFIG, ...options?.calibrationConfig };
  }

  async start() {
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

    // Send initial VAD config to worklet
    this.workletNode.port.postMessage({
      type: 'vad-config',
      threshold: this.vadConfig.threshold,
      preRollSize: this.vadConfig.preRollSize,
      hangoverMax: this.vadConfig.hangoverMax,
    });

    this.workletNode.port.onmessage = (event: MessageEvent) => {
      if (event.data instanceof ArrayBuffer) {
        if (!this.gateSpeech) {
          const int16Array = new Int16Array(event.data);
          this.onAudio(int16Array);
        }
      } else if (event.data?.type === 'vad') {
        if (!this.gateSpeech) {
          this.onSpeechChange?.(event.data.isSpeech);
        }
      } else if (event.data?.type === 'rms') {
        this.handleRmsSample(event.data.value);
      } else if (event.data?.type === 'wake-word-frame') {
        this.handleWakeWordFrame(event.data.buffer);
      }
    };

    this.source.connect(this.workletNode);
    this.workletNode.connect(this.audioContext.destination);

    this.startCalibration();
  }

  private handleRmsSample(rms: number) {
    if (this.calibrationState.status === 'calibrating') {
      this.rmsSamples.push(rms);
    }
  }

  /**
   * Buffer wake word frames and feed to detector when we have enough samples.
   * The worklet emits 128-sample frames; Porcupine needs 512-sample frames.
   */
  private handleWakeWordFrame(buffer: ArrayBuffer) {
    if (!this.wakeWordDetector) return;

    const frame = new Int16Array(buffer);

    // Drop oldest frames if buffer exceeds limit
    if (this.wakeWordBufferedSamples + frame.length > this.MAX_WAKE_WORD_BUFFER_SAMPLES) {
      const dropped = this.wakeWordBuffer.shift();
      if (dropped) this.wakeWordBufferedSamples -= dropped.length;
    }

    this.wakeWordBuffer.push(frame);
    this.wakeWordBufferedSamples += frame.length;

    const needed = this.wakeWordDetector.frameLength;
    while (this.wakeWordBufferedSamples >= needed) {
      // Combine buffered frames into one detector-sized frame
      const combined = new Int16Array(needed);
      let offset = 0;
      while (offset < needed) {
        const chunk = this.wakeWordBuffer[0];
        const take = Math.min(chunk.length, needed - offset);
        combined.set(chunk.subarray(0, take), offset);
        offset += take;

        if (take < chunk.length) {
          // Partial consume — keep remainder
          this.wakeWordBuffer[0] = chunk.subarray(take);
        } else {
          this.wakeWordBuffer.shift();
        }
      }
      this.wakeWordBufferedSamples -= needed;

      const detected = this.wakeWordDetector.process(combined);
      if (detected) {
        this.wakeWordCallback?.();
      }
    }
  }

  private async startCalibration() {
    const token = Symbol('calibration');
    this.calibrationToken = token;
    this.gateSpeech = true;
    this.rmsSamples = [];
    this.updateCalibrationState({ status: 'calibrating' });

    await new Promise<void>((resolve) =>
      window.setTimeout(resolve, this.calibrationConfig.durationMs),
    );
    this.finishCalibration(token);
  }

  private finishCalibration(token: symbol) {
    if (this.calibrationToken !== token) return;

    const { threshold, usedFallback } = computeCalibrationThreshold(
      this.rmsSamples,
      this.calibrationConfig,
      this.vadConfig.threshold,
    );
    this.setVADThreshold(threshold);
    // Only ungated if wake word is not active — otherwise stay gated
    if (!this.wakeWordDetector) {
      this.gateSpeech = false;
    }
    if (usedFallback) {
      this.updateCalibrationState({
        status: 'error',
        error: 'No audio samples collected',
        threshold,
      });
    } else {
      this.updateCalibrationState({ status: 'ready', threshold });
    }
  }

  private updateCalibrationState(state: CalibrationState) {
    this.calibrationState = state;
    this.onCalibrationChange?.(state);
  }

  recalibrate() {
    if (!this.workletNode) return;
    this.startCalibration();
  }

  getCalibrationState(): CalibrationState {
    return this.calibrationState;
  }

  setVADThreshold(threshold: number) {
    this.vadConfig.threshold = threshold;
    this.workletNode?.port.postMessage({ type: 'vad-config', threshold });
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
   * Enable wake word detection. Gates audio (stops forwarding to backend)
   * and routes worklet frames to the detector instead.
   */
  enableWakeWord(detector: WakeWordDetector, onDetected: () => void): void {
    this.wakeWordDetector = detector;
    this.wakeWordCallback = onDetected;
    this.wakeWordBuffer = [];
    this.wakeWordBufferedSamples = 0;
    this.gateSpeech = true;
    this.onSpeechChange?.(false);
    this.workletNode?.port.postMessage({ type: 'wake-word-config', enabled: true });
  }

  /**
   * Disable wake word detection. Ungates audio so it flows to the backend.
   */
  disableWakeWord(): void {
    this.wakeWordDetector = null;
    this.wakeWordCallback = null;
    this.wakeWordBuffer = [];
    this.wakeWordBufferedSamples = 0;
    this.gateSpeech = false;
    this.workletNode?.port.postMessage({ type: 'wake-word-config', enabled: false });
  }

  pause() {
    this.gateSpeech = true;
    this.onSpeechChange?.(false);
  }

  resume() {
    this.gateSpeech = false;
  }

  stop() {
    this.calibrationToken = null;
    this.wakeWordDetector?.release();
    this.wakeWordDetector = null;
    this.source?.disconnect();
    this.workletNode?.disconnect();
    this.workletNode?.port.close();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.audioContext?.close();
  }
}
