/**
 * Factory for creating wake word detectors based on environment configuration.
 *
 * Reads `VITE_WAKE_WORD_ENGINE` to determine which engine to instantiate.
 * Each engine implementation wraps a specific SDK behind the common
 * `WakeWordDetector` interface.
 */
import type { WakeWordDetector } from './wakeWordDetector';

export type WakeWordEngine = 'porcupine' | 'sherpa-onnx' | 'openwakeword';

export interface WakeWordFactoryConfig {
  engine: WakeWordEngine;
}

/**
 * Create a WakeWordDetector for the configured engine.
 *
 * Each engine reads its own env vars for model paths, API keys, etc.
 * The returned detector is engine-agnostic — consumers only see the
 * `WakeWordDetector` interface.
 */
export async function createWakeWordDetector(
  config: WakeWordFactoryConfig,
): Promise<WakeWordDetector> {
  switch (config.engine) {
    case 'porcupine': {
      const { PorcupineDetector } = await import('./porcupineDetector');
      const accessKey = import.meta.env.VITE_PORCUPINE_ACCESS_KEY || '';
      if (!accessKey) {
        throw new Error('VITE_PORCUPINE_ACCESS_KEY is required for Porcupine engine');
      }
      return PorcupineDetector.create({
        accessKey,
        keyword: {
          publicPath: '/models/porcupine/tank_wake_word.ppn',
          label: 'Hey Tank',
        },
        model: {
          publicPath: '/models/porcupine/porcupine_params.pv',
        },
      });
    }

    case 'sherpa-onnx': {
      const { SherpaOnnxKwsDetector } = await import('./sherpaOnnxKwsDetector');
      const modelDir = import.meta.env.VITE_SHERPA_ONNX_KWS_MODEL_DIR || '/models/sherpa-onnx-kws';
      return SherpaOnnxKwsDetector.create({ modelDir });
    }

    case 'openwakeword': {
      const { OpenWakeWordDetector } = await import('./openWakeWordDetector');
      const modelDir = import.meta.env.VITE_OPENWAKEWORD_MODEL_DIR || '/models/openwakeword';
      const keyword = import.meta.env.VITE_OPENWAKEWORD_KEYWORD || 'hey_jarvis';
      return OpenWakeWordDetector.create({ modelDir, keyword });
    }

    default:
      throw new Error(`Unknown wake word engine: ${config.engine}`);
  }
}
