/**
 * Porcupine wake word detector — wraps @picovoice/porcupine-web.
 *
 * Porcupine runs in a Web Worker. Its `process()` is fire-and-forget:
 * it posts audio to the worker and fires `keywordDetectionCallback`
 * asynchronously when a keyword is detected. We bridge this to the
 * synchronous `WakeWordDetector.process()` interface via a flag.
 */
import {
  PorcupineWorker,
  type PorcupineKeyword,
  type PorcupineModel,
} from '@picovoice/porcupine-web';

import type { WakeWordDetector } from './wakeWordDetector';

export interface PorcupineDetectorConfig {
  accessKey: string;
  keyword: PorcupineKeyword;
  model: PorcupineModel;
  sensitivity?: number;
}

export class PorcupineDetector implements WakeWordDetector {
  readonly frameLength: number;
  readonly sampleRate: number;

  private worker: PorcupineWorker;
  private _detected = false;

  private constructor(worker: PorcupineWorker) {
    this.worker = worker;
    this.frameLength = worker.frameLength;
    this.sampleRate = worker.sampleRate;
  }

  /**
   * Create and initialize a PorcupineDetector.
   * Must be called before `process()`.
   */
  static async create(config: PorcupineDetectorConfig): Promise<PorcupineDetector> {
    const worker = await PorcupineWorker.create(
      config.accessKey,
      [config.keyword],
      (detection) => {
        console.log(`Wake word detected: "${detection.label}"`);
        detector._detected = true;
      },
      config.model,
    );

    const detector = new PorcupineDetector(worker);
    return detector;
  }

  /**
   * Feed a frame of Int16 PCM audio.
   * Returns true if the wake word was detected since the last call.
   *
   * The frame MUST be exactly `frameLength` samples long.
   */
  process(frame: Int16Array): boolean {
    const wasDetected = this._detected;
    this._detected = false;

    // Fire-and-forget: posts to worker, callback sets _detected
    this.worker.process(frame);

    // Return the detection from the PREVIOUS frame's callback.
    // There's a 1-frame latency, which is ~32ms — imperceptible.
    return wasDetected;
  }

  release(): void {
    this.worker.terminate();
  }
}
