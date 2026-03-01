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
    this.gateSpeech = false;
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

  stop() {
    this.calibrationToken = null;
    this.source?.disconnect();
    this.workletNode?.disconnect();
    this.workletNode?.port.close();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.audioContext?.close();
  }
}
