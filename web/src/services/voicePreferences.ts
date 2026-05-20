/**
 * User preferences for voice interaction: how the mic listens, whether
 * the assistant speaks back, and (for wake-word mode) whether voice can
 * interrupt the assistant mid-response. Persisted in localStorage.
 */

export type ListenMode = 'continuous' | 'wake_word' | 'ptt';

export interface VoicePreferences {
  listenMode: ListenMode;
  voiceInterruptEnabled: boolean;
  /** Whether chat mode also speaks responses aloud. Voice mode always speaks. */
  chatSpeakEnabled: boolean;
}

const STORAGE_KEY = 'tank.voicePreferences';

const LISTEN_MODES: readonly ListenMode[] = ['continuous', 'wake_word', 'ptt'];

function isListenMode(value: unknown): value is ListenMode {
  return typeof value === 'string' && (LISTEN_MODES as readonly string[]).includes(value);
}

export function getDefaultPreferences(wakeWordAvailable: boolean): VoicePreferences {
  return {
    listenMode: wakeWordAvailable ? 'wake_word' : 'continuous',
    voiceInterruptEnabled: false,
    chatSpeakEnabled: false,
  };
}

export function loadVoicePreferences(wakeWordAvailable: boolean): VoicePreferences {
  const defaults = getDefaultPreferences(wakeWordAvailable);
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    let listenMode = isListenMode(parsed.listenMode) ? parsed.listenMode : defaults.listenMode;
    // Migrate legacy 'off' mode → 'ptt'
    if (parsed.listenMode === 'off') {
      listenMode = 'ptt';
    }
    // If wake word isn't available in this build, silently downgrade.
    if (listenMode === 'wake_word' && !wakeWordAvailable) {
      listenMode = 'continuous';
    }
    return {
      listenMode,
      voiceInterruptEnabled:
        typeof parsed.voiceInterruptEnabled === 'boolean'
          ? parsed.voiceInterruptEnabled
          : defaults.voiceInterruptEnabled,
      chatSpeakEnabled:
        typeof parsed.chatSpeakEnabled === 'boolean'
          ? parsed.chatSpeakEnabled
          : defaults.chatSpeakEnabled,
    };
  } catch {
    return defaults;
  }
}

export function storeVoicePreferences(prefs: VoicePreferences): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // localStorage may be unavailable (Safari private mode, quota, etc.) — ignore.
  }
}
