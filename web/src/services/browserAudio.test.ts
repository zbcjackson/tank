import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { BrowserAudioAdapter } from './browserAudio';

// --- Mock AudioContext ---
let mockContextInstance: {
  currentTime: number;
  createBuffer: ReturnType<typeof vi.fn>;
  createBufferSource: ReturnType<typeof vi.fn>;
  createAnalyser: ReturnType<typeof vi.fn>;
  destination: object;
  close: ReturnType<typeof vi.fn>;
  sampleRate: number;
};

let mockSourceNode: {
  buffer: AudioBuffer | null;
  connect: ReturnType<typeof vi.fn>;
  start: ReturnType<typeof vi.fn>;
};

let mockAnalyserNode: {
  fftSize: number;
  smoothingTimeConstant: number;
  minDecibels: number;
  maxDecibels: number;
  connect: ReturnType<typeof vi.fn>;
};

function setupMockAudioContext() {
  mockSourceNode = {
    buffer: null,
    connect: vi.fn(),
    start: vi.fn(),
  };

  mockAnalyserNode = {
    fftSize: 0,
    smoothingTimeConstant: 0,
    minDecibels: 0,
    maxDecibels: 0,
    connect: vi.fn(),
  };

  const mockBuffer = {
    duration: 0.5, // 500ms
    getChannelData: vi.fn().mockReturnValue(new Float32Array(12000)),
  };

  mockContextInstance = {
    currentTime: 0,
    createBuffer: vi.fn().mockReturnValue(mockBuffer),
    createBufferSource: vi.fn().mockReturnValue(mockSourceNode),
    createAnalyser: vi.fn().mockReturnValue(mockAnalyserNode),
    destination: {},
    close: vi.fn().mockResolvedValue(undefined),
    sampleRate: 24000,
  };

  vi.stubGlobal(
    'AudioContext',
    vi.fn().mockImplementation(() => mockContextInstance),
  );
}

describe('BrowserAudioAdapter', () => {
  let adapter: BrowserAudioAdapter;

  beforeEach(() => {
    setupMockAudioContext();
    adapter = new BrowserAudioAdapter();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('playChunk creates AudioContext lazily and schedules audio', async () => {
    const data = new Int16Array([100, 200, -100]).buffer;
    const result = await adapter.playChunk(data);

    expect(mockContextInstance.createBufferSource).toHaveBeenCalled();
    expect(mockSourceNode.start).toHaveBeenCalled();
    expect(result.durationMs).toBeGreaterThan(0);
  });

  it('stopPlayback closes AudioContext', async () => {
    await adapter.playChunk(new Int16Array([1]).buffer);
    await adapter.stopPlayback();

    expect(mockContextInstance.close).toHaveBeenCalled();
    expect(adapter.getAnalyserNode()).toBeNull();
  });

  it('stopPlayback sets stopped flag — subsequent playChunk is rejected', async () => {
    await adapter.playChunk(new Int16Array([1]).buffer);
    await adapter.stopPlayback();

    // Reset mock to track new calls
    vi.mocked(AudioContext).mockClear();

    const result = await adapter.playChunk(new Int16Array([2]).buffer);
    // Should return 0 duration and NOT create a new AudioContext
    expect(result.durationMs).toBe(0);
    expect(AudioContext).not.toHaveBeenCalled();
  });

  it('resetPlayback clears stopped flag — playChunk works again', async () => {
    await adapter.playChunk(new Int16Array([1]).buffer);
    await adapter.stopPlayback();
    adapter.resetPlayback();

    // Need fresh mock since old context was closed
    setupMockAudioContext();

    const result = await adapter.playChunk(new Int16Array([3]).buffer);
    expect(result.durationMs).toBeGreaterThan(0);
    expect(mockSourceNode.start).toHaveBeenCalled();
  });
});
