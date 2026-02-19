export class AudioProcessor {
  private audioContext: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private processor: ScriptProcessorNode | null = null;
  private onAudio: (data: Int16Array) => void;

  constructor(onAudio: (data: Int16Array) => void) {
    this.onAudio = onAudio;
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

    this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({
      sampleRate: 16000,
    });

    this.source = this.audioContext.createMediaStreamSource(this.stream);
    
    // Using ScriptProcessor for simplicity in this prototype. 
    // AudioWorklet is preferred but more complex to setup with Vite.
    this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);

    this.processor.onaudioprocess = (e) => {
      const inputData = e.inputBuffer.getChannelData(0);
      
      // Convert Float32 to Int16 PCM
      const int16Array = new Int16Array(inputData.length);
      for (let i = 0; i < inputData.length; i++) {
        const s = Math.max(-1, Math.min(1, inputData[i]));
        int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }
      
      this.onAudio(int16Array);
    };

    if (this.source && this.processor) {
      this.source.connect(this.processor);
      this.processor.connect(this.audioContext.destination);
    }
  }

  stop() {
    this.source?.disconnect();
    this.processor?.disconnect();
    this.stream?.getTracks().forEach(t => t.stop());
    this.audioContext?.close();
  }
}
