import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AudioPlayback } from './audioPlayback';
import type { PlatformAudioAdapter } from './platformAudio';

/** Build a framed audio buffer matching the backend's encode_audio_frame. */
function frame(pcmLen: number, sampleRate = 24000, channels = 1): ArrayBuffer {
  const header = new ArrayBuffer(8);
  const view = new DataView(header);
  view.setUint16(0, 0x544b, true); // magic "TK"
  view.setUint32(2, sampleRate, true);
  view.setUint16(6, channels, true);
  const out = new Uint8Array(8 + pcmLen);
  out.set(new Uint8Array(header), 0);
  return out.buffer;
}

function createMockAdapter(): PlatformAudioAdapter {
  return {
    startCapture: vi.fn().mockResolvedValue({ stop: vi.fn() }),
    playChunk: vi.fn().mockResolvedValue({ durationMs: 500 }),
    stopPlayback: vi.fn().mockResolvedValue(undefined),
    resetPlayback: vi.fn(),
    getAnalyserNode: vi.fn().mockReturnValue(null),
    setOnRmsChange: vi.fn(),
    dispose: vi.fn().mockResolvedValue(undefined),
  };
}

describe('AudioPlayback', () => {
  let playback: AudioPlayback;
  let adapter: PlatformAudioAdapter;
  let speakingChanges: boolean[];

  beforeEach(() => {
    vi.useFakeTimers();
    playback = new AudioPlayback();
    adapter = createMockAdapter();
    playback.setPlatformAdapter(adapter);
    speakingChanges = [];
    playback.setOnSpeakingChange((s) => speakingChanges.push(s));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('play() decodes frame header and passes rate/channels to adapter', async () => {
    await playback.play(frame(100, 22050, 2));
    expect(adapter.playChunk).toHaveBeenCalledTimes(1);
    const [pcm, sr, ch] = vi.mocked(adapter.playChunk).mock.calls[0];
    expect((pcm as ArrayBuffer).byteLength).toBe(100);
    expect(sr).toBe(22050);
    expect(ch).toBe(2);
    expect(speakingChanges).toContain(true);
  });

  it('play() schedules speaking=false after duration', async () => {
    await playback.play(frame(100));
    expect(speakingChanges.at(-1)).toBe(true);
    vi.advanceTimersByTime(500);
    expect(speakingChanges.at(-1)).toBe(false);
  });

  it('stop() calls adapter.stopPlayback and sets speaking=false', async () => {
    await playback.play(frame(100));
    speakingChanges.length = 0;
    playback.stop();
    expect(adapter.stopPlayback).toHaveBeenCalled();
    expect(speakingChanges.at(-1)).toBe(false);
  });

  it('stop() prevents subsequent play() from producing audio', async () => {
    playback.stop();
    await playback.play(frame(100));
    expect(adapter.playChunk).not.toHaveBeenCalled();
  });

  it('reset() re-enables playback after stop()', async () => {
    playback.stop();
    playback.reset();
    await playback.play(frame(100));
    expect(adapter.playChunk).toHaveBeenCalledTimes(1);
  });

  it('stop() clears pending speaking timer so it does not fire again', async () => {
    await playback.play(frame(100));
    playback.stop();
    const countAfterStop = speakingChanges.length;
    vi.advanceTimersByTime(1000);
    expect(speakingChanges.length).toBe(countAfterStop);
  });

  it('reset() calls adapter.resetPlayback', () => {
    playback.stop();
    playback.reset();
    expect(adapter.resetPlayback).toHaveBeenCalled();
  });

  it('play() swallows malformed frames (bad magic) without calling adapter', async () => {
    const badFrame = new ArrayBuffer(16);
    new DataView(badFrame).setUint16(0, 0xdead, true);
    await playback.play(badFrame);
    expect(adapter.playChunk).not.toHaveBeenCalled();
  });
});
