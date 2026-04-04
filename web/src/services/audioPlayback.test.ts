import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AudioPlayback } from './audioPlayback';
import type { PlatformAudioAdapter } from './platformAudio';

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

  it('play() delegates to adapter and sets speaking=true', async () => {
    await playback.play(new ArrayBuffer(100));
    expect(adapter.playChunk).toHaveBeenCalledTimes(1);
    expect(speakingChanges).toContain(true);
  });

  it('play() schedules speaking=false after duration', async () => {
    await playback.play(new ArrayBuffer(100));
    expect(speakingChanges.at(-1)).toBe(true);
    vi.advanceTimersByTime(500);
    expect(speakingChanges.at(-1)).toBe(false);
  });

  it('stop() calls adapter.stopPlayback and sets speaking=false', async () => {
    await playback.play(new ArrayBuffer(100));
    speakingChanges.length = 0;
    playback.stop();
    expect(adapter.stopPlayback).toHaveBeenCalled();
    expect(speakingChanges.at(-1)).toBe(false);
  });

  it('stop() prevents subsequent play() from producing audio', async () => {
    playback.stop();
    await playback.play(new ArrayBuffer(100));
    expect(adapter.playChunk).not.toHaveBeenCalled();
  });

  it('reset() re-enables playback after stop()', async () => {
    playback.stop();
    playback.reset();
    await playback.play(new ArrayBuffer(100));
    expect(adapter.playChunk).toHaveBeenCalledTimes(1);
  });

  it('stop() clears pending speaking timer so it does not fire again', async () => {
    await playback.play(new ArrayBuffer(100));
    playback.stop();
    const countAfterStop = speakingChanges.length;
    // Advance past the original timer — should NOT fire an additional callback
    vi.advanceTimersByTime(1000);
    expect(speakingChanges.length).toBe(countAfterStop);
  });

  it('reset() calls adapter.resetPlayback', () => {
    playback.stop();
    playback.reset();
    expect(adapter.resetPlayback).toHaveBeenCalled();
  });
});
