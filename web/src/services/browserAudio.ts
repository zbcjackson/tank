/**
 * Browser implementation of PlatformAudioAdapter.
 *
 * Owns the AudioContext + AnalyserNode for Web Audio API playback.
 * Capture is handled externally by AudioProcessor (getUserMedia + AudioWorklet),
 * so startCapture() is a no-op here.
 */

import type { PlatformAudioAdapter, CaptureHandle, PlayChunkResult } from './platformAudio';

export class BrowserAudioAdapter implements PlatformAudioAdapter {
  private audioContext: AudioContext | null = null;
  private analyserNode: AnalyserNode | null = null;
  private nextStartTime: number = 0;

  /** Ensure AudioContext + AnalyserNode exist (lazy init on first playback). */
  private ensureAudioContext() {
    if (!this.audioContext) {
      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      this.audioContext = new AudioCtx({ sampleRate: 24000 });
      this.nextStartTime = this.audioContext.currentTime;

      this.analyserNode = this.audioContext.createAnalyser();
      this.analyserNode.fftSize = 1024;
      this.analyserNode.smoothingTimeConstant = 0.7;
      this.analyserNode.minDecibels = -70;
      this.analyserNode.maxDecibels = -20;
      this.analyserNode.connect(this.audioContext.destination);
    }
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async startCapture(onAudio: (samples: Int16Array) => void): Promise<CaptureHandle> {
    // Browser capture is handled by AudioProcessor (getUserMedia + AudioWorklet).
    return { stop() {} };
  }

  async playChunk(data: ArrayBuffer): Promise<PlayChunkResult> {
    this.ensureAudioContext();

    const int16Array = new Int16Array(data);
    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 32768.0;
    }

    const buffer = this.audioContext!.createBuffer(1, float32Array.length, 24000);
    buffer.getChannelData(0).set(float32Array);

    const source = this.audioContext!.createBufferSource();
    source.buffer = buffer;
    source.connect(this.analyserNode!);

    const startTime = Math.max(this.nextStartTime, this.audioContext!.currentTime);
    source.start(startTime);
    this.nextStartTime = startTime + buffer.duration;

    // Duration until the last scheduled sample finishes
    const delayMs = (this.nextStartTime - this.audioContext!.currentTime) * 1000;
    return { durationMs: delayMs };
  }

  async stopPlayback(): Promise<void> {
    if (this.audioContext) {
      await this.audioContext.close();
      this.audioContext = null;
      this.analyserNode = null;
      this.nextStartTime = 0;
    }
  }

  getAnalyserNode(): AnalyserNode | null {
    return this.analyserNode;
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  setOnRmsChange(cb: ((rms: number) => void) | null): void {
    // Browser uses AnalyserNode for waveform — RMS callback not needed.
  }

  async dispose(): Promise<void> {
    await this.stopPlayback();
  }
}
