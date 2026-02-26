class AudioCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    // VAD config — 128 samples/frame at 16kHz = 8ms/frame
    this.rmsThreshold = 0.01;
    this.preRollSize = 25;   // 200ms ÷ 8ms — buffer before speech onset
    this.hangoverMax = 188;  // 1500ms ÷ 8ms — send silence after speech for ASR endpoint detection

    // State
    this.isSpeech = false;
    this.hangoverCount = 0;
    this.ringBuffer = [];    // recent silence frames for pre-roll

    // Accept runtime config updates from main thread
    this.port.onmessage = (event) => {
      if (event.data && event.data.type === 'vad-config') {
        const cfg = event.data;
        if (cfg.threshold !== undefined) this.rmsThreshold = cfg.threshold;
        if (cfg.preRollSize !== undefined) this.preRollSize = cfg.preRollSize;
        if (cfg.hangoverMax !== undefined) this.hangoverMax = cfg.hangoverMax;
      }
    };
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0] || input[0].length === 0) {
      return true;
    }

    const float32 = input[0];

    // Convert Float32 → Int16
    const int16 = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      const s = Math.max(-1, Math.min(1, float32[i]));
      int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }

    // Compute RMS energy
    let sumSq = 0;
    for (let i = 0; i < float32.length; i++) {
      sumSq += float32[i] * float32[i];
    }
    const rms = Math.sqrt(sumSq / float32.length);
    // Emit RMS so the main thread can calibrate ambient noise
    this.port.postMessage({ type: 'rms', value: rms });
    const speechDetected = rms >= this.rmsThreshold;

    if (speechDetected) {
      // Speech onset — flush pre-roll then send current frame
      if (!this.isSpeech) {
        this.isSpeech = true;
        this.port.postMessage({ type: 'vad', isSpeech: true });

        for (const buf of this.ringBuffer) {
          this.port.postMessage(buf, [buf]);
        }
        this.ringBuffer = [];
      }

      this.hangoverCount = this.hangoverMax;
      this.port.postMessage(int16.buffer, [int16.buffer]);
    } else if (this.isSpeech) {
      // In hangover — keep sending so backend ASR finishes the utterance
      this.hangoverCount--;
      this.port.postMessage(int16.buffer, [int16.buffer]);

      if (this.hangoverCount <= 0) {
        this.isSpeech = false;
        this.hangoverCount = 0;
        this.port.postMessage({ type: 'vad', isSpeech: false });
      }
    } else {
      // Idle silence — don't send, just buffer for pre-roll
      const copy = int16.buffer.slice(0);
      this.ringBuffer.push(copy);
      if (this.ringBuffer.length > this.preRollSize) {
        this.ringBuffer.shift();
      }
    }

    return true;
  }
}

registerProcessor('audio-capture-processor', AudioCaptureProcessor);
