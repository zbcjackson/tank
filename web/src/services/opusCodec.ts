/**
 * WebCodecs opus codec wrapper (protocol plan P1-2).
 *
 * The web client negotiates the `opus` feature only when WebCodecs
 * AudioEncoder/AudioDecoder support the codec (Chrome/Edge/Firefox/modern
 * Safari); otherwise the connection stays on raw PCM — zero payload cost,
 * native libopus in the browser, no wasm bundle for Tauri to ship.
 *
 * WebCodecs pins opus at 48 kHz. The negotiated OPUS_PROFILE rates describe
 * the *server-side* decode rates and don't constrain the browser: any opus
 * packet decodes at any rate, so downlink packets decode to 48 kHz mono
 * float, and the 16 kHz mic stream is linearly upsampled before encoding.
 * All packets are standard libopus and interoperate with the other clients.
 */

const OPUS_CODEC_RATE = 48000;
const UPLINK_CAPTURE_RATE = 16000;

/** Rate opus packets decode to in the browser (WebCodecs pins opus at 48 kHz). */
export const OPUS_DECODE_SAMPLE_RATE = OPUS_CODEC_RATE;

const ENCODER_CONFIG: AudioEncoderConfig = {
  codec: 'opus',
  sampleRate: OPUS_CODEC_RATE,
  numberOfChannels: 1,
  bitrate: 32000,
  opus: { format: 'opus' },
};

const DECODER_CONFIG: AudioDecoderConfig = {
  codec: 'opus',
  sampleRate: OPUS_CODEC_RATE,
  numberOfChannels: 1,
};

interface WebCodecsGlobals {
  AudioEncoder?: typeof AudioEncoder;
  AudioDecoder?: typeof AudioDecoder;
}

function globals(): WebCodecsGlobals {
  return globalThis as unknown as WebCodecsGlobals;
}

/** True when this browser can encode and decode raw opus packets. */
export async function isOpusSupported(): Promise<boolean> {
  const { AudioEncoder, AudioDecoder } = globals();
  if (!AudioEncoder || !AudioDecoder) return false;
  // TS 5.9's lib.dom omits the spec's `supported` flag — guard structurally.
  const hasSupported = (r: unknown): r is { supported: boolean } =>
    typeof r === 'object' && r !== null && 'supported' in r;
  try {
    const [enc, dec] = await Promise.all([
      AudioEncoder.isConfigSupported(ENCODER_CONFIG),
      AudioDecoder.isConfigSupported(DECODER_CONFIG),
    ]);
    return hasSupported(enc) && hasSupported(dec) && enc.supported && dec.supported;
  } catch (e) {
    console.error('[opus] support probe failed:', e);
    return false;
  }
}

/** Linear 3× upsample 16 kHz → 48 kHz (opus encoder input is pinned at 48 kHz). */
export function upsample3x(input: Int16Array): Float32Array<ArrayBuffer> {
  const out = new Float32Array(input.length * 3);
  for (let i = 0; i < input.length; i++) {
    const a = input[i] / 32768;
    if (i + 1 < input.length) {
      const b = input[i + 1] / 32768;
      const step = (b - a) / 3;
      out[i * 3] = a;
      out[i * 3 + 1] = a + step;
      out[i * 3 + 2] = a + 2 * step;
    } else {
      out[i * 3] = a;
      out[i * 3 + 1] = a;
      out[i * 3 + 2] = a;
    }
  }
  return out;
}

/** Clamp float samples into int16 (playback path: opus → PCM wire frame). */
export function float32ToInt16(input: Float32Array): Int16Array<ArrayBuffer> {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    out[i] = s < 0 ? s * 32768 : s * 32767;
  }
  return out;
}

/** Encodes 16 kHz mic frames into opus packets via WebCodecs AudioEncoder. */
export class OpusUplink {
  private encoder: AudioEncoder;
  private timestampUs = 0;

  constructor(
    onPacket: (packet: Uint8Array) => void,
    encoderCtor?: typeof AudioEncoder,
  ) {
    const Ctor = encoderCtor ?? globals().AudioEncoder;
    if (!Ctor) throw new Error('WebCodecs AudioEncoder unavailable');
    this.encoder = new Ctor({
      output: (chunk) => {
        const packet = new Uint8Array(chunk.byteLength);
        chunk.copyTo(packet);
        onPacket(packet);
      },
      error: (e) => console.error('[opus] uplink encoder error:', e),
    });
    // configure() + encode() queue in order — no readiness handshake needed.
    this.encoder.configure(ENCODER_CONFIG);
  }

  /** Feed one 16 kHz int16 mic frame; packets arrive via onPacket. */
  push(frame: Int16Array): void {
    const samples = upsample3x(frame);
    const data = new AudioData({
      format: 'f32-planar',
      sampleRate: OPUS_CODEC_RATE,
      numberOfFrames: samples.length,
      numberOfChannels: 1,
      timestamp: this.timestampUs,
      data: samples,
    });
    this.timestampUs += (frame.length / UPLINK_CAPTURE_RATE) * 1e6;
    this.encoder.encode(data);
    data.close();
  }

  /** Waits for all queued encodes to emit (end-of-stream / tests). */
  async flush(): Promise<void> {
    await this.encoder.flush();
  }

  dispose(): void {
    this.encoder.close();
  }
}

/** Decodes downlink opus packets into 48 kHz mono float via WebCodecs. */
export class OpusDownlink {
  private decoder: AudioDecoder;
  private timestampUs = 0;

  constructor(
    onAudio: (samples: Float32Array) => void,
    decoderCtor?: typeof AudioDecoder,
  ) {
    const Ctor = decoderCtor ?? globals().AudioDecoder;
    if (!Ctor) throw new Error('WebCodecs AudioDecoder unavailable');
    this.decoder = new Ctor({
      output: (audio) => {
        const samples = new Float32Array(audio.numberOfFrames);
        audio.copyTo(samples, { planeIndex: 0, format: 'f32-planar' });
        audio.close();
        onAudio(samples);
      },
      error: (e) => console.error('[opus] downlink decoder error:', e),
    });
    this.decoder.configure(DECODER_CONFIG);
  }

  /** Decode one wire opus packet; 48 kHz mono samples arrive via onAudio. */
  decode(packet: Uint8Array): void {
    this.decoder.decode(
      new EncodedAudioChunk({
        type: 'key',
        timestamp: this.timestampUs,
        data: packet,
      }),
    );
    this.timestampUs += 20000;
  }

  /** Waits for all queued decodes to emit (end-of-stream / tests). */
  async flush(): Promise<void> {
    await this.decoder.flush();
  }

  dispose(): void {
    this.decoder.close();
  }
}
