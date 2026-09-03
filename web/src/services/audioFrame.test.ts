import { describe, expect, it } from 'vitest';

import { AUDIO_FRAME_MAGIC, decodeAudioFrame, encodeAudioFrame } from './audioFrame';

describe('encodeAudioFrame / decodeAudioFrame round-trip', () => {
  it('preserves pcm, rate, and channels', () => {
    const pcm = new Int16Array([0, 16384, -16384, 32767]);
    const frame = encodeAudioFrame(pcm, 48000, 1);

    const { pcm: out, sampleRate, channels } = decodeAudioFrame(frame);
    expect(new Int16Array(out)).toEqual(pcm);
    expect(sampleRate).toBe(48000);
    expect(channels).toBe(1);
  });

  it('writes the 8-byte header with the wire magic', () => {
    const frame = encodeAudioFrame(new Int16Array([1]), 24000, 2);
    expect(frame.byteLength).toBe(8 + 2);
    const view = new DataView(frame);
    expect(view.getUint16(0, true)).toBe(AUDIO_FRAME_MAGIC);
    expect(view.getUint32(2, true)).toBe(24000);
    expect(view.getUint16(6, true)).toBe(2);
  });
});
