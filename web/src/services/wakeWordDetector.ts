/**
 * Engine-agnostic wake word detector interface.
 *
 * Implementations wrap a specific engine (Porcupine, sherpa-onnx, etc.)
 * and expose a uniform frame-processing API so the AudioProcessor and
 * conversation session hook don't care which engine is running underneath.
 */
export interface WakeWordDetector {
  /** Number of Int16 samples the engine expects per `process()` call. */
  readonly frameLength: number;

  /** Expected sample rate in Hz (e.g. 16000). */
  readonly sampleRate: number;

  /**
   * Feed a single audio frame to the detector.
   * @returns `true` if the wake word was detected in this frame.
   */
  process(frame: Int16Array): boolean;

  /** Release all resources held by the detector. */
  release(): void;
}
