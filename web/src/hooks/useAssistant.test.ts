import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

// Mock AudioProcessor so we can observe setBypassMicVad / pause / resume calls
const audioProcessorInstance = {
  setBypassMicVad: vi.fn(),
  setSpeaking: vi.fn(),
  setOnUtteranceEnd: vi.fn(),
  pause: vi.fn(),
  resume: vi.fn(),
  resumeForPtt: vi.fn(),
  pauseForPtt: vi.fn(),
  disableWakeWord: vi.fn().mockResolvedValue(undefined),
  enableWakeWord: vi.fn().mockResolvedValue(undefined),
  start: vi.fn().mockResolvedValue(undefined),
  stop: vi.fn(),
  setPlatformAdapter: vi.fn(),
};
vi.mock('../services/audio', () => ({
  AudioProcessor: vi.fn().mockImplementation(() => audioProcessorInstance),
}));

// Mock VoiceAssistantClient so we can observe sendMessage and feed in messages
const clientInstance = {
  connect: vi.fn(),
  disconnect: vi.fn(),
  reconnect: vi.fn(),
  sendAudio: vi.fn(),
  sendMessage: vi.fn(),
  sendInterrupt: vi.fn(),
};
vi.mock('../services/websocket', () => ({
  VoiceAssistantClient: vi.fn().mockImplementation(() => clientInstance),
}));

// Mock playback to avoid Web Audio API in jsdom
const playbackInstance = {
  setPlatformAdapter: vi.fn(),
  setOnSpeakingChange: vi.fn(),
  play: vi.fn(),
  stop: vi.fn(),
  reset: vi.fn(),
  dispose: vi.fn(),
  getAnalyserNode: vi.fn().mockReturnValue(null),
};
vi.mock('../services/audioPlayback', () => ({
  AudioPlayback: vi.fn().mockImplementation(() => playbackInstance),
}));

// Mock platformAudio adapter creation
vi.mock('../services/platformAudio', () => ({
  createPlatformAudio: vi.fn().mockResolvedValue({
    dispose: vi.fn(),
    setOnRmsChange: vi.fn(),
    startCapture: vi.fn(),
    getAnalyserNode: vi.fn().mockReturnValue(null),
  }),
}));

import { useAssistant } from './useAssistant';

describe('useAssistant — listen mode bypass orchestration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    // Default wake-word availability — useListenMode reads VITE_WAKE_WORD_ENABLED
    // at import time; tests below switch listen mode explicitly.
  });

  /** Helper: wait until audioReady becomes true (AudioProcessor.start resolved + capabilities set). */
  async function primeAudio(result: { current: ReturnType<typeof useAssistant> }) {
    // Feed capabilities so useAudioPipeline starts the AudioProcessor.
    const connect = clientInstance.connect.mock.calls[0];
    expect(connect).toBeDefined();
    const onMessage = connect[0] as (msg: Record<string, unknown>) => void;

    act(() => {
      onMessage({
        type: 'signal',
        content: 'ready',
        is_user: false,
        is_final: true,
        metadata: { capabilities: { asr: true, tts: true, speaker_id: false } },
      });
    });

    await waitFor(() => {
      expect(audioProcessorInstance.start).toHaveBeenCalled();
    });
    // The pipeline awaits start().then(setAudioReady(true)) — wait for the
    // bypass effect to run once.
    await waitFor(() => {
      // After audioReady becomes true, the listen-mode effect runs.
      // Default mode is voice + (wake_word if built, else continuous).
      expect(audioProcessorInstance.setBypassMicVad).toHaveBeenCalled();
    });
    return result;
  }

  it('continuous mode with mic ON enables bypass and resumes processor', async () => {
    const { result } = renderHook(() => useAssistant('test-session'));
    await primeAudio(result);

    // Select continuous mode (in jsdom the wake-word build flag is off so
    // continuous is the default — but call setListenMode explicitly to be deterministic).
    act(() => {
      result.current.setListenMode('continuous');
    });

    // Mic starts OFF — listenMode change resets isContinuousMicOn.
    // Toggle it ON.
    audioProcessorInstance.setBypassMicVad.mockClear();
    audioProcessorInstance.resume.mockClear();
    act(() => {
      result.current.toggleContinuousMic();
    });

    await waitFor(() => {
      expect(audioProcessorInstance.setBypassMicVad).toHaveBeenCalledWith(true);
    });
    expect(audioProcessorInstance.resume).toHaveBeenCalled();
  });

  it('continuous mode with mic OFF disables bypass and pauses processor', async () => {
    const { result } = renderHook(() => useAssistant('test-session'));
    await primeAudio(result);

    // Switch to ptt first (a real transition from default 'continuous'),
    // then back to 'continuous' so the listen-mode effect re-runs with
    // mic OFF and we can observe the bypass=false + pause() calls.
    act(() => {
      result.current.setListenMode('ptt');
    });

    audioProcessorInstance.setBypassMicVad.mockClear();
    audioProcessorInstance.pause.mockClear();

    act(() => {
      result.current.setListenMode('continuous');
    });

    await waitFor(() => {
      expect(audioProcessorInstance.setBypassMicVad).toHaveBeenCalledWith(false);
    });
    expect(audioProcessorInstance.pause).toHaveBeenCalled();
  });

  it('ptt mode disables bypass', async () => {
    const { result } = renderHook(() => useAssistant('test-session'));
    await primeAudio(result);

    audioProcessorInstance.setBypassMicVad.mockClear();
    act(() => {
      result.current.setListenMode('ptt');
    });

    await waitFor(() => {
      expect(audioProcessorInstance.setBypassMicVad).toHaveBeenCalledWith(false);
    });
  });

  it('toggleContinuousMic off sends end_of_utterance signal then pauses', async () => {
    const { result } = renderHook(() => useAssistant('test-session'));
    await primeAudio(result);

    act(() => {
      result.current.setListenMode('continuous');
    });

    // Turn mic on
    act(() => {
      result.current.toggleContinuousMic();
    });
    expect(result.current.isContinuousMicOn).toBe(true);

    // Reset spies and toggle off
    clientInstance.sendMessage.mockClear();
    audioProcessorInstance.pause.mockClear();

    act(() => {
      result.current.toggleContinuousMic();
    });

    expect(result.current.isContinuousMicOn).toBe(false);
    // Signal sent before pause
    expect(clientInstance.sendMessage).toHaveBeenCalledWith('signal', 'end_of_utterance');
    expect(audioProcessorInstance.pause).toHaveBeenCalled();
    // Ordering: sendMessage call comes before pause call within the toggle handler
    const sendMessageOrder = clientInstance.sendMessage.mock.invocationCallOrder[0];
    const pauseOrder = audioProcessorInstance.pause.mock.invocationCallOrder[0];
    expect(sendMessageOrder).toBeLessThan(pauseOrder);
  });

  it('switching away from continuous mode with mic ON sends end_of_utterance', async () => {
    const { result } = renderHook(() => useAssistant('test-session'));
    await primeAudio(result);

    act(() => {
      result.current.setListenMode('continuous');
    });
    act(() => {
      result.current.toggleContinuousMic();
    });
    expect(result.current.isContinuousMicOn).toBe(true);

    clientInstance.sendMessage.mockClear();
    act(() => {
      result.current.setListenMode('ptt');
    });

    // Mode-switch effect should send end_of_utterance and reset isContinuousMicOn
    expect(clientInstance.sendMessage).toHaveBeenCalledWith('signal', 'end_of_utterance');
    expect(result.current.isContinuousMicOn).toBe(false);
  });
});
