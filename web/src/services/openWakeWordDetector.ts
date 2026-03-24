/**
 * openWakeWord detector — wraps openwakeword-wasm-browser package.
 *
 * Uses ONNX Runtime Web to run openWakeWord models entirely in the browser.
 * The WakeWordEngine manages its own mic capture via AudioWorklet.
 *
 * Setup:
 *   1. Install: pnpm add openwakeword-wasm-browser
 *   2. Place model files in `public/models/openwakeword/`:
 *      - melspectrogram.onnx, embedding_model.onnx, silero_vad.onnx
 *      - <keyword>.onnx (e.g., hey_jarvis.onnx or custom hey_tank.onnx)
 *   3. Set VITE_WAKE_WORD_ENGINE=openwakeword in .env
 */
import type { WakeWordDetector } from './wakeWordDetector';

/** Minimal type for the WakeWordEngine from openwakeword-wasm-browser */
interface WakeWordEngineOptions {
  baseAssetUrl: string;
  ortWasmPath?: string;
  keywords: string[];
  detectionThreshold: number;
  cooldownMs: number;
}

interface DetectionEvent {
  keyword: string;
  score: number;
  at: number;
}

interface WakeWordEngine {
  load(): Promise<void>;
  start(opts?: { deviceId?: string; gain?: number }): Promise<void>;
  stop(): Promise<void>;
  on(event: 'detect', cb: (e: DetectionEvent) => void): void;
  on(event: 'ready', cb: () => void): void;
  on(event: 'error', cb: (e: unknown) => void): void;
  on(event: 'speech-start', cb: () => void): void;
  on(event: 'speech-end', cb: () => void): void;
  setActiveKeywords(names: string[]): void;
  setGain(value: number): void;
}

interface WakeWordEngineConstructor {
  new (options: WakeWordEngineOptions): WakeWordEngine;
}

export interface OpenWakeWordDetectorConfig {
  /** Base URL path where ONNX model files are served (default: /models/openwakeword) */
  modelDir: string;
  /** Keyword model name without .onnx extension (e.g., "hey_jarvis") */
  keyword: string;
  /** Detection threshold 0-1 (default: 0.5) */
  threshold?: number;
  /** Cooldown between detections in ms (default: 2000) */
  cooldownMs?: number;
}

/** Map keyword model names to display labels */
const KEYWORD_LABELS: Record<string, string> = {
  hey_jarvis: 'Hey Jarvis',
  alexa: 'Alexa',
  hey_mycroft: 'Hey Mycroft',
  hey_rhasspy: 'Hey Rhasspy',
  hey_tank: 'Hey Tank',
};

export class OpenWakeWordDetector implements WakeWordDetector {
  readonly keyword: string;
  readonly frameLength = 1280; // 80ms at 16kHz
  readonly sampleRate = 16000;

  private engine: WakeWordEngine;
  private _onDetected: (() => void) | null = null;

  private constructor(engine: WakeWordEngine, keyword: string) {
    this.engine = engine;
    this.keyword = keyword;
  }

  /**
   * Create an OpenWakeWordDetector.
   *
   * Dynamically imports the openwakeword-wasm-browser package, creates the
   * engine, and loads ONNX models.
   */
  static async create(config: OpenWakeWordDetectorConfig): Promise<OpenWakeWordDetector> {
    const { modelDir, keyword, threshold = 0.5, cooldownMs = 2000 } = config;
    const displayLabel = KEYWORD_LABELS[keyword] ?? keyword.replace(/_/g, ' ');

    // Dynamic import to avoid bundling when not using this engine
    const mod = (await import('openwakeword-wasm-browser')) as {
      WakeWordEngine: WakeWordEngineConstructor;
    };

    const engine = new mod.WakeWordEngine({
      baseAssetUrl: modelDir,
      keywords: [keyword],
      detectionThreshold: threshold,
      cooldownMs,
    });

    // Load ONNX models (melspectrogram, embedding, VAD, keyword classifier)
    await engine.load();

    console.log(`[OpenWakeWord] Engine loaded with keyword="${keyword}"`);
    return new OpenWakeWordDetector(engine, displayLabel);
  }

  /**
   * Start listening for the wake word.
   * The engine manages its own mic capture via AudioWorklet.
   */
  async start(onDetected: () => void): Promise<void> {
    this._onDetected = onDetected;

    this.engine.on('detect', (event: DetectionEvent) => {
      console.log(
        `[OpenWakeWord] Keyword detected: "${event.keyword}" (score=${event.score.toFixed(3)})`,
      );
      this._onDetected?.();
    });

    this.engine.on('error', (err: unknown) => {
      console.error('[OpenWakeWord] Engine error:', err);
    });

    await this.engine.start();
    console.log('[OpenWakeWord] Started listening');
  }

  /**
   * Stop listening for the wake word. Stops mic capture.
   */
  async stop(): Promise<void> {
    this._onDetected = null;
    await this.engine.stop();
    console.log('[OpenWakeWord] Stopped listening');
  }

  /**
   * Release all resources held by the detector.
   */
  async release(): Promise<void> {
    await this.stop();
    console.log('[OpenWakeWord] Released');
  }
}
