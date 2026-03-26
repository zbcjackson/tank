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
  modelFiles?: Record<string, string>;
  detectionThreshold: number;
  cooldownMs: number;
  debug?: boolean;
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
  /** Model filename for the keyword (e.g., "hey_jarvis_v0.1.onnx"). Auto-resolved for built-in keywords. */
  modelFile?: string;
  /** Path to ONNX Runtime WASM files (default: let onnxruntime-web resolve via bundler) */
  ortWasmPath?: string;
  /** Detection threshold 0-1 (default: 0.25) */
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
  private _started = false;

  private constructor(engine: WakeWordEngine, keyword: string) {
    this.engine = engine;
    this.keyword = keyword;

    // Register event listeners once — they persist across start/stop cycles.
    // Detection is gated by _onDetected being non-null (set in start, cleared in stop).
    this.engine.on('detect', (event: DetectionEvent) => {
      console.log(
        `[OpenWakeWord] Keyword detected: "${event.keyword}" (score=${event.score.toFixed(3)})`,
      );
      this._onDetected?.();
    });

    this.engine.on('error', (err: unknown) => {
      console.error('[OpenWakeWord] Engine error:', err);
    });
  }

  /**
   * Create an OpenWakeWordDetector.
   *
   * Dynamically imports the openwakeword-wasm-browser package, creates the
   * engine, and loads ONNX models.
   */
  static async create(config: OpenWakeWordDetectorConfig): Promise<OpenWakeWordDetector> {
    const {
      modelDir,
      keyword,
      modelFile,
      ortWasmPath,
      threshold = 0.25,
      cooldownMs = 2000,
    } = config;
    const displayLabel = KEYWORD_LABELS[keyword] ?? keyword.replace(/_/g, ' ');

    // Dynamic import to avoid bundling when not using this engine
    const mod = (await import('openwakeword-wasm-browser')) as {
      WakeWordEngine: WakeWordEngineConstructor;
      MODEL_FILE_MAP: Record<string, string>;
    };

    // Build modelFiles map: start with built-in defaults, add/override for custom keywords
    const modelFiles: Record<string, string> = { ...mod.MODEL_FILE_MAP };
    if (modelFile) {
      modelFiles[keyword] = modelFile;
    } else if (!(keyword in modelFiles)) {
      // Auto-resolve: look for <keyword>*.onnx pattern
      modelFiles[keyword] = `${keyword}_v0.1.onnx`;
    }

    const engineOpts: WakeWordEngineOptions = {
      baseAssetUrl: modelDir,
      ortWasmPath: '/ort/',
      keywords: [keyword],
      modelFiles,
      detectionThreshold: threshold,
      cooldownMs,
    };

    if (ortWasmPath) {
      engineOpts.ortWasmPath = ortWasmPath;
    }

    const engine = new mod.WakeWordEngine(engineOpts);

    // Load ONNX models (melspectrogram, embedding, VAD, keyword classifier)
    await engine.load();

    console.log(`[OpenWakeWord] Engine loaded with keyword="${keyword}"`);
    return new OpenWakeWordDetector(engine, displayLabel);
  }

  /**
   * Start listening for the wake word.
   *
   * The engine's audio pipeline is started once and kept running across
   * start/stop cycles. Only the detection callback is toggled — this avoids
   * re-creating AudioContext + AudioWorklet on every re-arm, which the
   * underlying library doesn't handle reliably.
   */
  async start(onDetected: () => void): Promise<void> {
    this._onDetected = onDetected;
    if (!this._started) {
      await this.engine.start();
      this._started = true;
      console.log('[OpenWakeWord] Started listening');
    } else {
      console.log('[OpenWakeWord] Re-armed detection callback');
    }
  }

  /**
   * Stop listening for the wake word.
   * Only clears the callback — the engine's audio pipeline stays alive
   * so it can be re-armed quickly without rebuilding the AudioWorklet.
   */
  async stop(): Promise<void> {
    this._onDetected = null;
    console.log('[OpenWakeWord] Detection paused (engine still running)');
  }

  /**
   * Release all resources held by the detector.
   * This is the only method that actually stops the engine's audio pipeline.
   */
  async release(): Promise<void> {
    this._onDetected = null;
    if (this._started) {
      await this.engine.stop();
      this._started = false;
    }
    console.log('[OpenWakeWord] Released');
  }
}
