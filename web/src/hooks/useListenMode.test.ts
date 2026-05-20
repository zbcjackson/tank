import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useListenMode } from './useListenMode';
import { storeVoicePreferences } from '../services/voicePreferences';

describe('useListenMode', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('initializes from stored prefs when present', () => {
    storeVoicePreferences({
      listenMode: 'ptt',
      voiceInterruptEnabled: true,
      chatSpeakEnabled: true,
    });
    const { result } = renderHook(() => useListenMode({ wakeWordAvailable: true }));
    expect(result.current.listenMode).toBe('ptt');
    expect(result.current.chatSpeakEnabled).toBe(true);
    expect(result.current.voiceInterruptEnabled).toBe(true);
  });

  it('initializes to wake_word default when wake word is available and no stored prefs', () => {
    const { result } = renderHook(() => useListenMode({ wakeWordAvailable: true }));
    expect(result.current.listenMode).toBe('wake_word');
  });

  it('initializes to continuous when wake word is not available', () => {
    const { result } = renderHook(() => useListenMode({ wakeWordAvailable: false }));
    expect(result.current.listenMode).toBe('continuous');
  });

  it('persists listenMode changes to localStorage', () => {
    const { result } = renderHook(() => useListenMode({ wakeWordAvailable: true }));
    act(() => result.current.setListenMode('ptt'));
    expect(result.current.listenMode).toBe('ptt');
    expect(JSON.parse(localStorage.getItem('tank.voicePreferences') || '{}').listenMode).toBe(
      'ptt',
    );
  });

  it('persists chatSpeakEnabled changes to localStorage', () => {
    const { result } = renderHook(() => useListenMode({ wakeWordAvailable: true }));
    act(() => result.current.setChatSpeakEnabled(true));
    expect(result.current.chatSpeakEnabled).toBe(true);
    expect(JSON.parse(localStorage.getItem('tank.voicePreferences') || '{}').chatSpeakEnabled).toBe(
      true,
    );
  });

  it('persists voiceInterruptEnabled changes', () => {
    const { result } = renderHook(() => useListenMode({ wakeWordAvailable: true }));
    act(() => result.current.setVoiceInterruptEnabled(true));
    expect(result.current.voiceInterruptEnabled).toBe(true);
  });

  it('refuses to switch to wake_word when build flag is off', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { result } = renderHook(() => useListenMode({ wakeWordAvailable: false }));
    act(() => result.current.setListenMode('wake_word'));
    expect(result.current.listenMode).toBe('continuous');
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('downgrades wake_word to continuous if availability flips off after mount', () => {
    storeVoicePreferences({
      listenMode: 'wake_word',
      voiceInterruptEnabled: false,
      chatSpeakEnabled: false,
    });
    const { result, rerender } = renderHook(
      ({ wakeWordAvailable }: { wakeWordAvailable: boolean }) =>
        useListenMode({ wakeWordAvailable }),
      { initialProps: { wakeWordAvailable: true } },
    );
    expect(result.current.listenMode).toBe('wake_word');
    rerender({ wakeWordAvailable: false });
    expect(result.current.listenMode).toBe('continuous');
  });
});
