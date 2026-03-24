/**
 * Sherpa-ONNX keyword spotting detector — wraps sherpa-onnx WASM KWS.
 *
 * Uses the Emscripten-compiled sherpa-onnx WASM build for on-device keyword
 * spotting. Models are pre-loaded into the Emscripten virtual filesystem via
 * the `.data` file at build time. Manages its own AudioContext +
 * ScriptProcessorNode to capture mic audio and feed frames to the recognizer.
 *
 * Setup:
 *   1. Build WASM KWS from sherpa-onnx source (./build-wasm-simd-kws.sh)
 *   2. Copy output to `public/models/sherpa-onnx-kws/`:
 *      - sherpa-onnx-kws.js          (JS API wrapper defining createKws)
 *      - sherpa-onnx-wasm-kws-main.js (Emscripten glue)
 *      - sherpa-onnx-wasm-kws-main.wasm
 *      - sherpa-onnx-wasm-kws-main.data (bundled model files)
 *   3. Set VITE_WAKE_WORD_ENGINE=sherpa-onnx in .env
 */
import type { WakeWordDetector } from './wakeWordDetector';

/** Minimal type for the sherpa-onnx WASM Emscripten module */
interface SherpaOnnxModule {
  onRuntimeInitialized: (() => void) | null;
  locateFile?: (path: string) => string;
}

/** Kws recognizer returned by createKws() */
interface KwsRecognizer {
  createStream(): KwsStream;
  isReady(stream: KwsStream): boolean;
  decode(stream: KwsStream): void;
  getResult(stream: KwsStream): { keyword: string };
  reset(stream: KwsStream): void;
  free(): void;
}

interface KwsStream {
  acceptWaveform(sampleRate: number, samples: Float32Array): void;
  inputFinished(): void;
  free(): void;
}

/** Declared at global scope by sherpa-onnx-kws.js */
declare function createKws(module: SherpaOnnxModule, config?: SherpaOnnxKwsConfig): KwsRecognizer;

interface SherpaOnnxKwsConfig {
  featConfig: { samplingRate: number; featureDim: number };
  modelConfig: {
    transducer: { encoder: string; decoder: string; joiner: string };
    tokens: string;
    provider: string;
    modelType: string;
    numThreads: number;
    debug: number;
    modelingUnit: string;
    bpeVocab: string;
  };
  maxActivePaths: number;
  numTrailingBlanks: number;
  keywordsScore: number;
  keywordsThreshold: number;
  keywords: string;
}

export interface SherpaOnnxKwsDetectorConfig {
  /** Base URL path where WASM build files are served (default: /models/sherpa-onnx-kws) */
  modelDir: string;
  /** Wake word keyword label for UI display (default: Hey Tank) */
  keywordLabel?: string;
  /**
   * Tokenized keyword string for the recognizer.
   * Format: space-separated phoneme tokens with @DisplayName suffix.
   * Default: "HH EY1 T AE1 NG K @Hey Tank" (ARPAbet for "Hey Tank")
   */
  keywordsTokens?: string;
}

/** Default keyword: "Hey Tank" encoded as ARPAbet phonemes for zh-en model */
const DEFAULT_KEYWORDS = 'HH EY1 T AE1 NG K @HEY_TANK';

/**
 * Load a JS script dynamically and wait for it to execute.
 */
function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      resolve();
      return;
    }
    const script = document.createElement('script');
    script.src = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load script: ${src}`));
    document.head.appendChild(script);
  });
}

/**
 * Downsample audio buffer from source sample rate to target sample rate.
 * Uses simple averaging (same approach as the sherpa-onnx WASM demo).
 */
function downsampleBuffer(
  buffer: Float32Array,
  sourceSampleRate: number,
  targetSampleRate: number,
): Float32Array {
  if (sourceSampleRate === targetSampleRate) return buffer;
  if (sourceSampleRate < targetSampleRate) {
    throw new Error(`Source rate ${sourceSampleRate} < target rate ${targetSampleRate}`);
  }

  const ratio = sourceSampleRate / targetSampleRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);

  let offsetResult = 0;
  let offsetBuffer = 0;

  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let accum = 0;
    let count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
      accum += buffer[i];
      count++;
    }
    result[offsetResult] = accum / count;
    offsetResult++;
    offsetBuffer = nextOffsetBuffer;
  }

  return result;
}

export class SherpaOnnxKwsDetector implements WakeWordDetector {
  readonly keyword: string;
  readonly frameLength = 4096;
  readonly sampleRate = 16000;

  private recognizer: KwsRecognizer;
  private stream: KwsStream | null = null;
  private audioContext: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private scriptNode: ScriptProcessorNode | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private _onDetected: (() => void) | null = null;

  private constructor(recognizer: KwsRecognizer, keyword: string) {
    this.recognizer = recognizer;
    this.keyword = keyword;
  }

  /**
   * Create a SherpaOnnxKwsDetector.
   *
   * Loads the WASM build scripts, waits for Emscripten to initialize (which
   * also loads the .data file containing model weights into the VFS), then
   * creates the KWS recognizer with the specified keyword.
   */
  static async create(config: SherpaOnnxKwsDetectorConfig): Promise<SherpaOnnxKwsDetector> {
    const modelDir = config.modelDir;
    const keywordLabel = config.keywordLabel ?? 'Hey Tank';
    const keywordsTokens = config.keywordsTokens ?? DEFAULT_KEYWORDS;

    // Step 1: Set up the global Module object BEFORE loading any scripts.
    // The Emscripten glue script checks `typeof Module != "undefined"` at
    // parse time, so Module must exist before the script tag executes.
    const module = await new Promise<SherpaOnnxModule>((resolve, reject) => {
      const mod: SherpaOnnxModule = {
        onRuntimeInitialized: () => {
          console.log('[SherpaOnnxKws] WASM runtime initialized');
          resolve(mod);
        },
        // Tell Emscripten where to find .wasm and .data files
        locateFile: (path: string) => `${modelDir}/${path}`,
      };
      (window as unknown as Record<string, unknown>).Module = mod;

      // Step 2: Load scripts in sequence:
      // - sherpa-onnx-kws.js defines createKws() (must come first)
      // - sherpa-onnx-wasm-kws-main.js boots the WASM module (reads Module global)
      loadScript(`${modelDir}/sherpa-onnx-kws.js`)
        .then(() => loadScript(`${modelDir}/sherpa-onnx-wasm-kws-main.js`))
        .catch(reject);

      setTimeout(() => reject(new Error('Sherpa-ONNX WASM module load timeout (30s)')), 30000);
    });

    // Step 3: Create KWS recognizer. Model files are already in the Emscripten
    // VFS (loaded from .data). We call createKws() without a config override
    // so it uses the built-in defaults (correct VFS paths, modelingUnit, etc.)
    // then patch only the keywords afterward via a second call.
    //
    // NOTE: createKws(module, myConfig) REPLACES the entire default config
    // (not merge), so we must provide a complete config if overriding.
    const recognizer = createKws(module, {
      featConfig: { samplingRate: 16000, featureDim: 80 },
      modelConfig: {
        transducer: {
          encoder: './encoder-epoch-12-avg-2-chunk-16-left-64.onnx',
          decoder: './decoder-epoch-12-avg-2-chunk-16-left-64.onnx',
          joiner: './joiner-epoch-12-avg-2-chunk-16-left-64.onnx',
        },
        tokens: './tokens.txt',
        provider: 'cpu',
        modelType: '',
        numThreads: 1,
        debug: 1,
        modelingUnit: 'cjkchar',
        bpeVocab: '',
      },
      maxActivePaths: 4,
      numTrailingBlanks: 1,
      keywordsScore: 1.0,
      keywordsThreshold: 0.25,
      keywords: keywordsTokens,
    });

    console.log(`[SherpaOnnxKws] Recognizer created with keywords: "${keywordsTokens}"`);
    return new SherpaOnnxKwsDetector(recognizer, keywordLabel);
  }

  /**
   * Start listening for the wake word.
   * Sets up mic capture via AudioContext + ScriptProcessorNode,
   * feeds frames to the WASM recognizer, and calls onDetected on match.
   */
  async start(onDetected: () => void): Promise<void> {
    this._onDetected = onDetected;
    this.stream = this.recognizer.createStream();

    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, sampleRate: { ideal: this.sampleRate } },
    });

    this.audioContext = new AudioContext({ sampleRate: this.sampleRate });
    const actualSampleRate = this.audioContext.sampleRate;

    this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);

    // ScriptProcessorNode for frame-by-frame processing.
    // Deprecated but widely supported; AudioWorklet would require WASM in a worker.
    this.scriptNode = this.audioContext.createScriptProcessor(this.frameLength, 1, 1);

    const stream = this.stream;
    const recognizer = this.recognizer;
    const targetSampleRate = this.sampleRate;
    const getOnDetected = () => this._onDetected;

    this.scriptNode.onaudioprocess = (event: AudioProcessingEvent) => {
      const cb = getOnDetected();
      if (!stream || !cb) return;

      const inputData = event.inputBuffer.getChannelData(0);
      const samples =
        actualSampleRate !== targetSampleRate
          ? downsampleBuffer(inputData, actualSampleRate, targetSampleRate)
          : inputData;

      stream.acceptWaveform(targetSampleRate, samples);

      while (recognizer.isReady(stream)) {
        recognizer.decode(stream);
        const result = recognizer.getResult(stream);

        if (result.keyword.length > 0) {
          console.log(`[SherpaOnnxKws] Keyword detected: "${result.keyword}"`);
          recognizer.reset(stream);
          cb();
        }
      }
    };

    this.sourceNode.connect(this.scriptNode);
    this.scriptNode.connect(this.audioContext.destination);

    console.log(
      `[SherpaOnnxKws] Started listening (sampleRate=${actualSampleRate}, target=${this.sampleRate})`,
    );
  }

  /** Stop listening for the wake word. Tears down audio capture. */
  async stop(): Promise<void> {
    this._onDetected = null;

    this.scriptNode?.disconnect();
    this.scriptNode = null;

    this.sourceNode?.disconnect();
    this.sourceNode = null;

    if (this.audioContext) {
      await this.audioContext.close();
      this.audioContext = null;
    }

    this.mediaStream?.getTracks().forEach((t) => t.stop());
    this.mediaStream = null;

    this.stream?.free();
    this.stream = null;

    console.log('[SherpaOnnxKws] Stopped listening');
  }

  /** Release all resources held by the detector. */
  async release(): Promise<void> {
    await this.stop();
    this.recognizer.free();
    console.log('[SherpaOnnxKws] Released');
  }
}
