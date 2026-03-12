/**
 * Engine-agnostic wake word detector interface.
 *
 * Implementations wrap a specific engine (Porcupine, sherpa-onnx, etc.)
 * and expose a callback-based API. The detector manages its own audio
 * pipeline internally (e.g. via WebVoiceProcessor for Porcupine).
 */
export interface WakeWordDetector {
  /** Number of Int16 samples the engine expects per frame. */
  readonly frameLength: number;

  /** Expected sample rate in Hz (e.g. 16000). */
  readonly sampleRate: number;

  /** Start listening for the wake word. Calls `onDetected` when heard. */
  start(onDetected: () => void): Promise<void>;

  /** Stop listening for the wake word. */
  stop(): Promise<void>;

  /** Release all resources held by the detector. */
  release(): void;
}
