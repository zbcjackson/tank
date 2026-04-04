import { describe, expect, it, vi, beforeEach } from 'vitest';
import { AudioProcessor } from './audio';

// Mock MicVAD — capture callbacks so tests can trigger them
let vadCallbacks: Record<string, (...args: unknown[]) => void> = {};
const mockVadInstance = {
  start: vi.fn().mockResolvedValue(undefined),
  pause: vi.fn().mockResolvedValue(undefined),
  destroy: vi.fn().mockResolvedValue(undefined),
  listening: true,
};

vi.mock('@ricky0123/vad-web', () => ({
  MicVAD: {
    new: vi.fn().mockImplementation(async (opts: Record<string, unknown>) => {
      vadCallbacks = {
        onSpeechStart: opts.onSpeechStart as () => void,
        onSpeechEnd: opts.onSpeechEnd as () => void,
        onVADMisfire: opts.onVADMisfire as () => void,
      };
      return mockVadInstance;
    }),
  },
}));

describe('AudioProcessor', () => {
  it('can be instantiated with just an onAudio callback', () => {
    const processor = new AudioProcessor(() => {});
    expect(processor).toBeDefined();
  });

  describe('dual-gate logic', () => {
    let processor: AudioProcessor;
    let received: Int16Array[];

    beforeEach(() => {
      vi.clearAllMocks();
      vadCallbacks = {};
      received = [];
      processor = new AudioProcessor((data) => received.push(data));
    });

    /**
     * Helper: simulate browser start() by calling the private initVad + setting gates.
     * We can't call real start() (needs getUserMedia), so we reach in via the public API
     * and trigger initVad through a controlled path.
     */
    async function simulateBrowserStart(proc: AudioProcessor) {
      // Set a fake stream so initVad proceeds
      const fakeStream = { getAudioTracks: () => [] } as unknown as MediaStream;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (proc as any).stream = fakeStream;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await (proc as any).initVad();
      // Simulate what start() does after initVad
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (proc as any).gateSpeech = false;
    }

    /** Helper: push a frame through the private handler */
    function pushFrame(proc: AudioProcessor, frame: Int16Array) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (proc as any).handleCapturedFrame(frame);
    }

    it('blocks audio when vadOpen is false (no speech detected)', async () => {
      await simulateBrowserStart(processor);
      // gateSpeech=false, vadOpen=false (default before speech)
      pushFrame(processor, new Int16Array([1, 2, 3]));
      expect(received).toHaveLength(0);
    });

    it('forwards audio when both gates are open', async () => {
      await simulateBrowserStart(processor);
      vadCallbacks.onSpeechStart();
      pushFrame(processor, new Int16Array([10, 20]));
      expect(received).toHaveLength(1);
      expect(Array.from(received[0])).toEqual([10, 20]);
    });

    it('blocks audio when gateSpeech is true even if vadOpen', async () => {
      await simulateBrowserStart(processor);
      vadCallbacks.onSpeechStart();
      processor.pause(); // sets gateSpeech=true
      pushFrame(processor, new Int16Array([1]));
      expect(received).toHaveLength(0);
    });

    it('closes vadOpen on speech end', async () => {
      await simulateBrowserStart(processor);
      vadCallbacks.onSpeechStart();
      pushFrame(processor, new Int16Array([1]));
      expect(received).toHaveLength(1);

      vadCallbacks.onSpeechEnd(new Float32Array(0));
      pushFrame(processor, new Int16Array([2]));
      expect(received).toHaveLength(1); // no new frame forwarded
    });

    it('closes vadOpen on misfire', async () => {
      await simulateBrowserStart(processor);
      vadCallbacks.onSpeechStart();
      vadCallbacks.onVADMisfire();
      pushFrame(processor, new Int16Array([1]));
      expect(received).toHaveLength(0);
    });

    it('flushes pre-roll buffer on speech start', async () => {
      await simulateBrowserStart(processor);
      // Push frames while vadOpen=false — they go into pre-roll buffer
      pushFrame(processor, new Int16Array([1]));
      pushFrame(processor, new Int16Array([2]));
      pushFrame(processor, new Int16Array([3]));
      expect(received).toHaveLength(0);

      // Speech starts — pre-roll should flush
      vadCallbacks.onSpeechStart();
      expect(received).toHaveLength(3);
      expect(Array.from(received[0])).toEqual([1]);
      expect(Array.from(received[1])).toEqual([2]);
      expect(Array.from(received[2])).toEqual([3]);
    });
  });

  describe('setSpeaking (echo suppression)', () => {
    let processor: AudioProcessor;

    beforeEach(async () => {
      vi.clearAllMocks();
      vadCallbacks = {};
      processor = new AudioProcessor(() => {});
      const fakeStream = { getAudioTracks: () => [] } as unknown as MediaStream;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (processor as any).stream = fakeStream;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await (processor as any).initVad();
    });

    it('pauses MicVAD and opens vadOpen when speaking=true', () => {
      processor.setSpeaking(true);
      expect(mockVadInstance.pause).toHaveBeenCalled();
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect((processor as any).vadOpen).toBe(true);
    });

    it('resumes MicVAD when speaking=false', () => {
      processor.setSpeaking(true);
      processor.setSpeaking(false);
      expect(mockVadInstance.start).toHaveBeenCalled();
    });

    it('is a no-op when micVad is null', () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (processor as any).micVad = null;
      // Should not throw
      processor.setSpeaking(true);
      processor.setSpeaking(false);
    });
  });

  describe('graceful fallback', () => {
    it('sets vadOpen=true when MicVAD init fails', async () => {
      // Override the mock to reject
      const { MicVAD } = await import('@ricky0123/vad-web');
      vi.mocked(MicVAD.new).mockRejectedValueOnce(new Error('WASM not supported'));

      const processor = new AudioProcessor(() => {});
      const fakeStream = { getAudioTracks: () => [] } as unknown as MediaStream;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (processor as any).stream = fakeStream;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await (processor as any).initVad();

      // vadOpen should be true — gate always open, same as before this feature
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect((processor as any).vadOpen).toBe(true);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect((processor as any).micVad).toBeNull();
    });
  });

  describe('pause/resume with MicVAD', () => {
    let processor: AudioProcessor;

    beforeEach(async () => {
      vi.clearAllMocks();
      vadCallbacks = {};
      processor = new AudioProcessor(() => {});
      const fakeStream = { getAudioTracks: () => [] } as unknown as MediaStream;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (processor as any).stream = fakeStream;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await (processor as any).initVad();
    });

    it('pause() also pauses MicVAD', () => {
      processor.pause();
      expect(mockVadInstance.pause).toHaveBeenCalled();
    });

    it('resume() also starts MicVAD', () => {
      processor.pause();
      processor.resume();
      expect(mockVadInstance.start).toHaveBeenCalled();
    });
  });

  describe('stop cleanup', () => {
    it('destroys MicVAD on stop', async () => {
      vi.clearAllMocks();
      const processor = new AudioProcessor(() => {});
      const fakeStream = {
        getAudioTracks: () => [],
        getTracks: () => [],
      } as unknown as MediaStream;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (processor as any).stream = fakeStream;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await (processor as any).initVad();

      processor.stop();
      expect(mockVadInstance.destroy).toHaveBeenCalled();
    });
  });
});
