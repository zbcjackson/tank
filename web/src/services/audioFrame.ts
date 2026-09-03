/**
 * Wire format for streamed audio frames from the backend.
 * Must match `tank_contracts.tts.encode_audio_frame` (Python side).
 *
 * Layout (little-endian): magic(2) | sample_rate(4) | channels(2) | pcm_bytes...
 */

export const AUDIO_FRAME_MAGIC = 0x544b; // "TK"
export const AUDIO_FRAME_HEADER_SIZE = 8;

export interface DecodedAudioFrame {
  pcm: ArrayBuffer;
  sampleRate: number;
  channels: number;
}

export function decodeAudioFrame(frame: ArrayBuffer): DecodedAudioFrame {
  if (frame.byteLength < AUDIO_FRAME_HEADER_SIZE) {
    throw new Error(`audio frame too short: ${frame.byteLength}`);
  }
  const view = new DataView(frame);
  const magic = view.getUint16(0, true);
  if (magic !== AUDIO_FRAME_MAGIC) {
    throw new Error(`bad audio frame magic: 0x${magic.toString(16)}`);
  }
  const sampleRate = view.getUint32(2, true);
  const channels = view.getUint16(6, true);
  return {
    pcm: frame.slice(AUDIO_FRAME_HEADER_SIZE),
    sampleRate,
    channels,
  };
}

/** Build an 8-byte-header PCM frame — the reverse of decodeAudioFrame. Used
 * to re-frame opus-decoded PCM so downstream consumers stay header-typed. */
export function encodeAudioFrame(
  pcm: Int16Array,
  sampleRate: number,
  channels: number,
): ArrayBuffer {
  const out = new ArrayBuffer(AUDIO_FRAME_HEADER_SIZE + pcm.byteLength);
  const view = new DataView(out);
  view.setUint16(0, AUDIO_FRAME_MAGIC, true);
  view.setUint32(2, sampleRate, true);
  view.setUint16(6, channels, true);
  new Uint8Array(out, AUDIO_FRAME_HEADER_SIZE).set(
    new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength),
  );
  return out;
}
