/**
 * Browser implementation of PlatformAudioAdapter.
 *
 * Playback strategy: per-chunk `AudioBufferSourceNode`, scheduled at the
 * running `nextStartTime`. The `AudioBuffer` is created at the PCM's actual
 * sample rate (from the wire frame header), so Web Audio handles the
 * conversion to the device rate via its own resampler.
 *
 * Known limitation: on devices whose native output rate differs substantially
 * from the PCM rate (e.g. 192 kHz external DACs against 24 kHz TTS), the
 * per-buffer resampler state can produce audible artifacts at chunk joins.
 * A pull-model playback path (AudioWorklet ring buffer) can avoid this, but
 * requires a producer-rate-matched feed and pre-buffering that we don't
 * currently have — captured experimentation in this direction produced
 * dropouts (documented in the git history). For now we prefer the simple,
 * predictable per-chunk scheduling.
 *
 * Capture is handled externally by AudioProcessor (getUserMedia + AudioWorklet),
 * so startCapture() is a no-op here.
 */

import type { PlatformAudioAdapter, CaptureHandle, PlayChunkResult } from './platformAudio';

export class BrowserAudioAdapter implements PlatformAudioAdapter {
  private audioContext: AudioContext | null = null;
  private analyserNode: AnalyserNode | null = null;
  private nextStartTime: number = 0;
  private stopped: boolean = false;

  readonly handlesCapture = false;

  /** Ensure AudioContext + AnalyserNode exist (lazy init on first playback). */
  private ensureAudioContext(preferredRate: number) {
    if (!this.audioContext) {
      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      // Request the PCM's rate so the browser (if it honors the hint) runs
      // the graph at the source rate and resamples only once, at the output
      // stage. Falls back gracefully if the hint is not supported.
      try {
        this.audioContext = new AudioCtx({ sampleRate: preferredRate });
      } catch {
        this.audioContext = new AudioCtx();
      }
      this.nextStartTime = this.audioContext.currentTime;

      console.info(
        `[BrowserAudio] requested ${preferredRate}Hz, got ${this.audioContext.sampleRate}Hz ` +
          `(state=${this.audioContext.state})`,
      );

      this.analyserNode = this.audioContext.createAnalyser();
      this.analyserNode.fftSize = 1024;
      this.analyserNode.smoothingTimeConstant = 0.7;
      this.analyserNode.minDecibels = -70;
      this.analyserNode.maxDecibels = -20;
      this.analyserNode.connect(this.audioContext.destination);
    }
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async startCapture(_onAudio: (samples: Int16Array) => void): Promise<CaptureHandle> {
    // Browser capture is handled by AudioProcessor (getUserMedia + AudioWorklet).
    return { stop() {} };
  }

  async playChunk(
    data: ArrayBuffer,
    sampleRate: number,
    channels: number,
  ): Promise<PlayChunkResult> {
    if (this.stopped) return { durationMs: 0 };
    this.ensureAudioContext(sampleRate);

    // Defensive: trim odd-byte chunks so Int16Array never throws and drops
    // the entire chunk (the backend aligns already; this is belt-and-braces).
    const alignedByteLength = data.byteLength - (data.byteLength % 2);
    if (alignedByteLength === 0) return { durationMs: 0 };

    const int16Array = new Int16Array(data, 0, alignedByteLength / 2);
    const frameCount = Math.floor(int16Array.length / channels);
    if (frameCount === 0) return { durationMs: 0 };

    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 32768.0;
    }

    const buffer = this.audioContext!.createBuffer(channels, frameCount, sampleRate);
    if (channels === 1) {
      buffer.getChannelData(0).set(float32Array);
    } else {
      for (let c = 0; c < channels; c++) {
        const chData = buffer.getChannelData(c);
        for (let i = 0; i < frameCount; i++) {
          chData[i] = float32Array[i * channels + c];
        }
      }
    }

    const source = this.audioContext!.createBufferSource();
    source.buffer = buffer;
    source.connect(this.analyserNode!);

    const startTime = Math.max(this.nextStartTime, this.audioContext!.currentTime);
    source.start(startTime);
    this.nextStartTime = startTime + buffer.duration;

    const delayMs = (this.nextStartTime - this.audioContext!.currentTime) * 1000;
    return { durationMs: delayMs };
  }

  async stopPlayback(): Promise<void> {
    this.stopped = true;
    if (this.audioContext) {
      await this.audioContext.close();
      this.audioContext = null;
      this.analyserNode = null;
      this.nextStartTime = 0;
    }
  }

  resetPlayback(): void {
    this.stopped = false;
  }

  getAnalyserNode(): AnalyserNode | null {
    return this.analyserNode;
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  setOnRmsChange(_cb: ((rms: number) => void) | null): void {
    // Browser uses AnalyserNode for waveform — RMS callback not needed.
  }

  async dispose(): Promise<void> {
    await this.stopPlayback();
  }
}
