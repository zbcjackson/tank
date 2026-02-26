export interface VADConfig {
  threshold: number;
  preRollSize: number;  // frames (128 samples each at 16kHz)
  hangoverMax: number;  // frames
}

export const DEFAULT_VAD_CONFIG: VADConfig = {
  threshold: 0.01,
  preRollSize: 25,   // ~200ms
  hangoverMax: 188,   // ~1500ms — enough silence for backend ASR endpoint detection
};

interface AudioProcessorOptions {
  onSpeechChange?: (isSpeech: boolean) => void;
  vadConfig?: Partial<VADConfig>;
}

export class AudioProcessor {
  private audioContext: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private onAudio: (data: Int16Array) => void;
  private onSpeechChange?: (isSpeech: boolean) => void;
  private vadConfig: VADConfig;
  private muted = false;

  constructor(onAudio: (data: Int16Array) => void, options?: AudioProcessorOptions) {
    this.onAudio = onAudio;
    this.onSpeechChange = options?.onSpeechChange;
    this.vadConfig = { ...DEFAULT_VAD_CONFIG, ...options?.vadConfig };
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

    this.audioContext = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)({
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
        const int16Array = new Int16Array(event.data);
        this.onAudio(int16Array);
      } else if (event.data?.type === 'vad') {
        this.onSpeechChange?.(event.data.isSpeech);
      }
    };

    this.source.connect(this.workletNode);
    this.workletNode.connect(this.audioContext.destination);
  }

  setVADThreshold(threshold: number) {
    this.vadConfig.threshold = threshold;
    this.workletNode?.port.postMessage({ type: 'vad-config', threshold });
  }

  setMuted(muted: boolean) {
    this.muted = muted;
    this.stream?.getAudioTracks().forEach(track => {
      track.enabled = !muted;
    });
  }

  isMuted(): boolean {
    return this.muted;
  }

  stop() {
    this.source?.disconnect();
    this.workletNode?.disconnect();
    this.workletNode?.port.close();
    this.stream?.getTracks().forEach(t => t.stop());
    this.audioContext?.close();
  }
}
