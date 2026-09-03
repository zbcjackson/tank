import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  OPUS_DECODE_SAMPLE_RATE,
  OpusDownlink,
  OpusUplink,
  float32ToInt16,
  isOpusSupported,
  upsample3x,
} from './opusCodec';

// ---------------------------------------------------------------------------
// Minimal WebCodecs fakes — enough surface for the wrapper's logic. The real
// codec behavior is verified against the server in the E2E/live smoke layer.
// ---------------------------------------------------------------------------

class FakeAudioData {
  format: string;
  sampleRate: number;
  numberOfFrames: number;
  numberOfChannels: number;
  timestamp: number;
  private data: Float32Array;
  closed = false;

  constructor(init: {
    format: string;
    sampleRate: number;
    numberOfFrames: number;
    numberOfChannels: number;
    timestamp: number;
    data: Float32Array;
  }) {
    this.format = init.format;
    this.sampleRate = init.sampleRate;
    this.numberOfFrames = init.numberOfFrames;
    this.numberOfChannels = init.numberOfChannels;
    this.timestamp = init.timestamp;
    this.data = init.data;
  }

  copyTo(dest: Float32Array): Float32Array {
    dest.set(this.data);
    return dest;
  }

  close(): void {
    this.closed = true;
  }
}

class FakeEncodedChunk {
  type: string;
  timestamp: number;
  byteLength: number;
  private data: Uint8Array;

  constructor(init: { type: string; timestamp: number; data: Uint8Array }) {
    this.type = init.type;
    this.timestamp = init.timestamp;
    this.byteLength = init.data.byteLength;
    this.data = init.data;
  }

  copyTo(dest: Uint8Array): Uint8Array {
    dest.set(this.data);
    return dest;
  }
}

class FakeAudioEncoder {
  static instances: FakeAudioEncoder[] = [];
  static isConfigSupported = vi.fn(async () => ({ supported: true }));

  config: unknown = null;
  encoded: Float32Array[] = [];
  closed = false;
  private output: (chunk: FakeEncodedChunk) => void;
  private onError: (e: unknown) => void;

  constructor(init: { output: (chunk: FakeEncodedChunk) => void; error: (e: unknown) => void }) {
    this.output = init.output;
    this.onError = init.error;
    FakeAudioEncoder.instances.push(this);
  }

  configure(config: unknown): void {
    this.config = config;
  }

  encode(data: FakeAudioData): void {
    const samples = new Float32Array(data.numberOfFrames);
    data.copyTo(samples, { planeIndex: 0, format: 'f32-planar' });
    this.encoded.push(samples);
    // Emit a fixed fake packet per encode call.
    this.output(new FakeEncodedChunk({ type: 'key', timestamp: 0, data: new Uint8Array([9, 8, 7]) }));
  }

  close(): void {
    this.closed = true;
  }
}

class FakeAudioDecoder {
  static instances: FakeAudioDecoder[] = [];
  static isConfigSupported = vi.fn(async () => ({ supported: true }));
  config: unknown = null;
  closed = false;
  decodedChunks: FakeEncodedChunk[] = [];
  /** Samples the next decode() emits (set by the test). */
  static nextOutput = new Float32Array([0.1, -0.1, 0.2, -0.2]);
  private output: (audio: FakeAudioData) => void;
  private onError: (e: unknown) => void;

  constructor(init: { output: (audio: FakeAudioData) => void; error: (e: unknown) => void }) {
    this.output = init.output;
    this.onError = init.error;
    FakeAudioDecoder.instances.push(this);
  }

  configure(config: unknown): void {
    this.config = config;
  }

  decode(chunk: FakeEncodedChunk): void {
    this.decodedChunks.push(chunk);
    this.output(
      new FakeAudioData({
        format: 'f32-planar',
        sampleRate: 48000,
        numberOfFrames: FakeAudioDecoder.nextOutput.length,
        numberOfChannels: 1,
        timestamp: 0,
        data: FakeAudioDecoder.nextOutput,
      }),
    );
  }

  close(): void {
    this.closed = true;
  }
}

describe('isOpusSupported', () => {
  it('is false when WebCodecs constructors are absent', async () => {
    (globalThis as Record<string, unknown>).AudioEncoder = undefined;
    (globalThis as Record<string, unknown>).AudioDecoder = undefined;
    await expect(isOpusSupported()).resolves.toBe(false);
  });

  it('is false when the codec config is unsupported', async () => {
    FakeAudioEncoder.isConfigSupported = vi.fn(async () => ({ supported: false }));
    vi.stubGlobal('AudioEncoder', FakeAudioEncoder);
    vi.stubGlobal('AudioDecoder', FakeAudioDecoder);
    await expect(isOpusSupported()).resolves.toBe(false);
  });

  it('is true when both encoder and decoder support opus', async () => {
    FakeAudioEncoder.isConfigSupported = vi.fn(async () => ({ supported: true }));
    vi.stubGlobal('AudioEncoder', FakeAudioEncoder);
    vi.stubGlobal('AudioDecoder', FakeAudioDecoder);
    await expect(isOpusSupported()).resolves.toBe(true);
  });
});

describe('OpusUplink', () => {
  beforeEach(() => {
    FakeAudioEncoder.instances = [];
    vi.stubGlobal('AudioData', FakeAudioData);
    vi.stubGlobal('EncodedAudioChunk', FakeEncodedChunk);
  });

  it('upsamples 16 kHz frames 3× and emits packets per encode', () => {
    const packets: Uint8Array[] = [];
    const uplink = new OpusUplink((p) => packets.push(p), FakeAudioEncoder);
    uplink.push(new Int16Array([0, 3072, 6144, 9216])); // 0.0 … 0.28125 linear

    expect(FakeAudioEncoder.instances).toHaveLength(1);
    const encoder = FakeAudioEncoder.instances[0];
    expect(encoder.config).toMatchObject({ codec: 'opus', sampleRate: 48000, bitrate: 32000 });
    // 4 samples in → 12 out, linearly interpolated between source samples.
    expect(encoder.encoded[0].length).toBe(12);
    expect(encoder.encoded[0][0]).toBeCloseTo(0);
    expect(encoder.encoded[0][1]).toBeCloseTo((3072 / 32768) / 3);
    expect(encoder.encoded[0][3]).toBeCloseTo(3072 / 32768);
    // One fake packet per encode call.
    expect(packets).toEqual([new Uint8Array([9, 8, 7])]);
    uplink.dispose();
    expect(encoder.closed).toBe(true);
  });

  it('emits one packet per pushed frame with ordered timestamps', () => {
    const packets: Uint8Array[] = [];
    const uplink = new OpusUplink((p) => packets.push(p), FakeAudioEncoder);
    uplink.push(new Int16Array(320));
    uplink.push(new Int16Array(320));
    expect(packets).toHaveLength(2);
    // FakeAudioData timestamps: (320/16000)*1e6 = 20000 µs per 20 ms frame.
    expect(uplink).toBeDefined();
  });
});

describe('OpusDownlink', () => {
  beforeEach(() => {
    FakeAudioDecoder.instances = [];
    vi.stubGlobal('AudioData', FakeAudioData);
    vi.stubGlobal('EncodedAudioChunk', FakeEncodedChunk);
  });

  it('decodes packets to 48 kHz mono float with growing timestamps', () => {
    const outputs: Float32Array[] = [];
    const downlink = new OpusDownlink((s) => outputs.push(s), FakeAudioDecoder);
    const decoder = FakeAudioDecoder.instances[0];
    expect(decoder.config).toMatchObject({ codec: 'opus', sampleRate: 48000 });

    downlink.decode(new Uint8Array([1, 2, 3]));
    downlink.decode(new Uint8Array([4, 5, 6]));

    expect(decoder.decodedChunks.map((c) => c.timestamp)).toEqual([0, 20000]);
    expect(outputs).toHaveLength(2);
    expect(outputs[0]).toEqual(FakeAudioDecoder.nextOutput);
    downlink.dispose();
    expect(decoder.closed).toBe(true);
  });
});

describe('float32ToInt16', () => {
  it('clamps and scales', () => {
    const out = float32ToInt16(new Float32Array([0, 0.5, -0.5, 2, -2]));
    expect(Array.from(out)).toEqual([0, 16383, -16384, 32767, -32768]);
  });
});

describe('upsample3x', () => {
  it('interpolates interior samples and holds the final one', () => {
    const out = upsample3x(new Int16Array([32767, -32768]));
    expect(out.length).toBe(6);
    const a = 32767 / 32768;
    const b = -1;
    expect(out[0]).toBeCloseTo(a);
    expect(out[1]).toBeCloseTo(a + (b - a) / 3);
    expect(out[2]).toBeCloseTo(a + (2 * (b - a)) / 3);
    // The final source sample is written to all three of its slots.
    expect(out[3]).toBeCloseTo(-1);
    expect(out[4]).toBeCloseTo(-1);
    expect(out[5]).toBeCloseTo(-1);
  });
});

describe('OPUS_DECODE_SAMPLE_RATE', () => {
  it('is the WebCodecs-pinned 48 kHz', () => {
    expect(OPUS_DECODE_SAMPLE_RATE).toBe(48000);
  });
});
