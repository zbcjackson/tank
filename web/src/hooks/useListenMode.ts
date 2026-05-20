/**
 * Owns voice interaction preferences (listenMode, voiceInterruptEnabled,
 * chatSpeakEnabled) and persists them to localStorage.
 *
 * The hook intentionally does NOT trigger audio side effects (start/stop
 * detector, pause/resume mic). Those are owned by useAssistant, which
 * reacts to listenMode changes via effects. Keeping this hook
 * effect-free makes it trivially testable.
 */
import { useCallback, useMemo, useState } from 'react';

import {
  type ListenMode,
  type VoicePreferences,
  loadVoicePreferences,
  storeVoicePreferences,
} from '../services/voicePreferences';

export type { ListenMode, VoicePreferences };

export interface UseListenModeArgs {
  wakeWordAvailable: boolean;
}

export interface UseListenModeResult {
  listenMode: ListenMode;
  voiceInterruptEnabled: boolean;
  chatSpeakEnabled: boolean;
  setListenMode: (mode: ListenMode) => void;
  setVoiceInterruptEnabled: (enabled: boolean) => void;
  setChatSpeakEnabled: (enabled: boolean) => void;
}

export function useListenMode({ wakeWordAvailable }: UseListenModeArgs): UseListenModeResult {
  const [prefs, setPrefs] = useState<VoicePreferences>(() =>
    loadVoicePreferences(wakeWordAvailable),
  );

  // Effective listen mode: if availability has flipped to off (e.g. detector
  // was unloaded after mount), present 'continuous' to consumers without
  // mutating the stored preference. The user's intent is preserved — once
  // wake-word becomes available again, their stored choice resurfaces.
  const effectiveListenMode = useMemo<ListenMode>(
    () =>
      prefs.listenMode === 'wake_word' && !wakeWordAvailable ? 'continuous' : prefs.listenMode,
    [prefs.listenMode, wakeWordAvailable],
  );

  const setListenMode = useCallback(
    (mode: ListenMode) => {
      if (mode === 'wake_word' && !wakeWordAvailable) {
        console.warn('[useListenMode] wake_word selected but build flag is off — ignoring');
        return;
      }
      setPrefs((prev) => {
        const next = { ...prev, listenMode: mode };
        storeVoicePreferences(next);
        return next;
      });
    },
    [wakeWordAvailable],
  );

  const setVoiceInterruptEnabled = useCallback((enabled: boolean) => {
    setPrefs((prev) => {
      const next = { ...prev, voiceInterruptEnabled: enabled };
      storeVoicePreferences(next);
      return next;
    });
  }, []);

  const setChatSpeakEnabled = useCallback((enabled: boolean) => {
    setPrefs((prev) => {
      const next = { ...prev, chatSpeakEnabled: enabled };
      storeVoicePreferences(next);
      return next;
    });
  }, []);

  return {
    listenMode: effectiveListenMode,
    voiceInterruptEnabled: prefs.voiceInterruptEnabled,
    chatSpeakEnabled: prefs.chatSpeakEnabled,
    setListenMode,
    setVoiceInterruptEnabled,
    setChatSpeakEnabled,
  };
}
