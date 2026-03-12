/**
 * Porcupine wake word detector — wraps @picovoice/porcupine-web.
 *
 * Uses WebVoiceProcessor to feed audio to Porcupine's worker via the
 * official SDK pipeline. Detection is reported via a callback-based
 * WakeWordDetector interface.
 */
import {
  PorcupineWorker,
  BuiltInKeyword,
  type PorcupineKeyword,
  type PorcupineModel,
} from '@picovoice/porcupine-web';
import { WebVoiceProcessor } from '@picovoice/web-voice-processor';

import type { WakeWordDetector } from './wakeWordDetector';

export interface PorcupineDetectorConfig {
  accessKey: string;
  keyword?: PorcupineKeyword;
  builtinKeyword?: BuiltInKeyword;
  model: PorcupineModel;
  sensitivity?: number;
}

/**
 * Callback-based Porcupine detector.
 *
 * Instead of the synchronous `process(frame)` polling interface,
 * Porcupine manages its own mic via WebVoiceProcessor and fires
 * a callback on detection. The `onDetected` callback is set via
 * `start()` and cleared via `stop()`.
 */
export class PorcupineDetector implements WakeWordDetector {
  readonly frameLength: number;
  readonly sampleRate: number;

  private worker: PorcupineWorker;
  private _onDetected: (() => void) | null = null;
  private _subscribed = false;

  private constructor(worker: PorcupineWorker) {
    this.worker = worker;
    this.frameLength = worker.frameLength;
    this.sampleRate = worker.sampleRate;
  }

  static async create(config: PorcupineDetectorConfig): Promise<PorcupineDetector> {
    const keyword = config.keyword ?? config.builtinKeyword;
    if (!keyword) throw new Error('Either keyword or builtinKeyword must be provided');

    // eslint-disable-next-line prefer-const
    let detector: PorcupineDetector;

    const worker = await PorcupineWorker.create(
      config.accessKey,
      [keyword],
      (detection) => {
        console.log(
          `[Porcupine] Wake word detected: "${detection.label}" (index=${detection.index})`,
        );
        detector._onDetected?.();
      },
      config.model,
      {
        processErrorCallback: (error: string) => {
          console.error(`[Porcupine] Process error: ${error}`);
        },
      },
    );

    console.log(
      `[Porcupine] Worker created: frameLength=${worker.frameLength}, sampleRate=${worker.sampleRate}`,
    );

    detector = new PorcupineDetector(worker);
    return detector;
  }

  /**
   * Start listening for the wake word.
   * Subscribes to WebVoiceProcessor which feeds mic audio to Porcupine.
   */
  async start(onDetected: () => void): Promise<void> {
    this._onDetected = onDetected;
    if (!this._subscribed) {
      await WebVoiceProcessor.subscribe(this.worker);
      this._subscribed = true;
      console.log('[Porcupine] Subscribed to WebVoiceProcessor');
    }
  }

  /**
   * Stop listening. Unsubscribes from WebVoiceProcessor.
   */
  async stop(): Promise<void> {
    this._onDetected = null;
    if (this._subscribed) {
      await WebVoiceProcessor.unsubscribe(this.worker);
      this._subscribed = false;
      console.log('[Porcupine] Unsubscribed from WebVoiceProcessor');
    }
  }

  release(): void {
    if (this._subscribed) {
      WebVoiceProcessor.unsubscribe(this.worker);
      this._subscribed = false;
    }
    this.worker.terminate();
  }
}
