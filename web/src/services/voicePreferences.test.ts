import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  loadVoicePreferences,
  storeVoicePreferences,
  getDefaultPreferences,
} from './voicePreferences';

describe('voicePreferences', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  describe('getDefaultPreferences', () => {
    it('uses wake_word when available', () => {
      expect(getDefaultPreferences(true)).toEqual({
        listenMode: 'wake_word',
        voiceInterruptEnabled: false,
        chatSpeakEnabled: false,
      });
    });

    it('uses continuous when wake word unavailable', () => {
      expect(getDefaultPreferences(false).listenMode).toBe('continuous');
    });
  });

  describe('loadVoicePreferences', () => {
    it('returns defaults when storage is empty', () => {
      expect(loadVoicePreferences(false)).toEqual(getDefaultPreferences(false));
    });

    it('returns defaults when JSON is malformed', () => {
      localStorage.setItem('tank.voicePreferences', 'not-json{{');
      expect(loadVoicePreferences(true)).toEqual(getDefaultPreferences(true));
    });

    it('round-trips stored values', () => {
      const prefs = {
        listenMode: 'ptt',
        voiceInterruptEnabled: true,
        chatSpeakEnabled: true,
      } as const;
      storeVoicePreferences(prefs);
      expect(loadVoicePreferences(true)).toEqual(prefs);
    });

    it('falls back to default when listenMode is unknown', () => {
      localStorage.setItem(
        'tank.voicePreferences',
        JSON.stringify({ listenMode: 'mystery', voiceInterruptEnabled: false, chatSpeakEnabled: false }),
      );
      const loaded = loadVoicePreferences(true);
      expect(loaded.listenMode).toBe('wake_word');
    });

    it('silently downgrades wake_word when build flag is off', () => {
      storeVoicePreferences({
        listenMode: 'wake_word',
        voiceInterruptEnabled: false,
        chatSpeakEnabled: false,
      });
      expect(loadVoicePreferences(false).listenMode).toBe('continuous');
    });

    it('migrates legacy off mode to ptt', () => {
      localStorage.setItem(
        'tank.voicePreferences',
        JSON.stringify({ listenMode: 'off', voiceInterruptEnabled: false, chatSpeakEnabled: false }),
      );
      expect(loadVoicePreferences(true).listenMode).toBe('ptt');
    });

    it('uses default for non-boolean chatSpeakEnabled', () => {
      localStorage.setItem(
        'tank.voicePreferences',
        JSON.stringify({ listenMode: 'ptt', voiceInterruptEnabled: false, chatSpeakEnabled: 'yes' }),
      );
      expect(loadVoicePreferences(true).chatSpeakEnabled).toBe(false);
    });
  });

  describe('storeVoicePreferences', () => {
    it('does not throw when localStorage throws', () => {
      const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new Error('quota exceeded');
      });
      expect(() =>
        storeVoicePreferences({
          listenMode: 'continuous',
          voiceInterruptEnabled: false,
          chatSpeakEnabled: false,
        }),
      ).not.toThrow();
      setItem.mockRestore();
    });
  });
});
