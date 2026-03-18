import { describe, it, expect } from 'vitest';
import { statusReducer, type AssistantStatus, type StatusEvent } from './useAssistantStatus';

/** Helper: apply a sequence of events to an initial state */
function applyEvents(initial: AssistantStatus, events: StatusEvent[]): AssistantStatus {
  return events.reduce(statusReducer, initial);
}

describe('statusReducer', () => {
  describe('idle state', () => {
    it('transitions to thinking on PROCESSING_STARTED', () => {
      expect(statusReducer('idle', { type: 'PROCESSING_STARTED' })).toBe('thinking');
    });

    it('ignores irrelevant events', () => {
      const noOps: StatusEvent['type'][] = [
        'TEXT_DELTA',
        'TOOL_UPDATE',
        'TOOL_DONE',
        'SPEAKING_ENDED',
        'PROCESSING_ENDED',
      ];
      for (const type of noOps) {
        expect(statusReducer('idle', { type })).toBe('idle');
      }
    });

    it('transitions to speaking on AUDIO_CHUNK (late audio after processing_ended)', () => {
      expect(statusReducer('idle', { type: 'AUDIO_CHUNK' })).toBe('speaking');
    });
  });

  describe('thinking state', () => {
    it('transitions to tool_calling on TOOL_UPDATE', () => {
      expect(statusReducer('thinking', { type: 'TOOL_UPDATE' })).toBe('tool_calling');
    });

    it('transitions to responding on TEXT_DELTA', () => {
      expect(statusReducer('thinking', { type: 'TEXT_DELTA' })).toBe('responding');
    });

    it('transitions to speaking on AUDIO_CHUNK', () => {
      expect(statusReducer('thinking', { type: 'AUDIO_CHUNK' })).toBe('speaking');
    });

    it('transitions to idle on PROCESSING_ENDED', () => {
      expect(statusReducer('thinking', { type: 'PROCESSING_ENDED' })).toBe('idle');
    });

    it('can be interrupted', () => {
      expect(statusReducer('thinking', { type: 'INTERRUPT' })).toBe('interrupted');
    });

    it('can error', () => {
      expect(statusReducer('thinking', { type: 'ERROR' })).toBe('error');
    });
  });

  describe('tool_calling state', () => {
    it('transitions back to thinking on TOOL_DONE', () => {
      expect(statusReducer('tool_calling', { type: 'TOOL_DONE' })).toBe('thinking');
    });

    it('can be interrupted', () => {
      expect(statusReducer('tool_calling', { type: 'INTERRUPT' })).toBe('interrupted');
    });

    it('ignores TEXT_DELTA (tool still running)', () => {
      expect(statusReducer('tool_calling', { type: 'TEXT_DELTA' })).toBe('tool_calling');
    });
  });

  describe('responding state (chat mode text streaming)', () => {
    it('transitions to idle on PROCESSING_ENDED', () => {
      expect(statusReducer('responding', { type: 'PROCESSING_ENDED' })).toBe('idle');
    });

    it('transitions to speaking on AUDIO_CHUNK', () => {
      expect(statusReducer('responding', { type: 'AUDIO_CHUNK' })).toBe('speaking');
    });

    it('stays responding on additional TEXT_DELTA', () => {
      expect(statusReducer('responding', { type: 'TEXT_DELTA' })).toBe('responding');
    });

    it('can be interrupted', () => {
      expect(statusReducer('responding', { type: 'INTERRUPT' })).toBe('interrupted');
    });
  });

  describe('speaking state', () => {
    it('stays speaking on PROCESSING_ENDED (waits for audio to finish)', () => {
      expect(statusReducer('speaking', { type: 'PROCESSING_ENDED' })).toBe('speaking');
    });

    it('transitions to idle on SPEAKING_ENDED', () => {
      expect(statusReducer('speaking', { type: 'SPEAKING_ENDED' })).toBe('idle');
    });

    it('can be interrupted', () => {
      expect(statusReducer('speaking', { type: 'INTERRUPT' })).toBe('interrupted');
    });
  });

  describe('interrupted state (transient)', () => {
    it('transitions to idle on PROCESSING_ENDED', () => {
      expect(statusReducer('interrupted', { type: 'PROCESSING_ENDED' })).toBe('idle');
    });

    it('transitions to idle on RESET (safety timeout)', () => {
      expect(statusReducer('interrupted', { type: 'RESET' })).toBe('idle');
    });

    it('ignores further interrupts', () => {
      expect(statusReducer('interrupted', { type: 'INTERRUPT' })).toBe('interrupted');
    });
  });

  describe('error state (transient)', () => {
    it('transitions to idle on PROCESSING_ENDED', () => {
      expect(statusReducer('error', { type: 'PROCESSING_ENDED' })).toBe('idle');
    });

    it('transitions to idle on RESET (safety timeout)', () => {
      expect(statusReducer('error', { type: 'RESET' })).toBe('idle');
    });
  });

  describe('full conversation flows', () => {
    it('voice: idle → thinking → speaking → idle', () => {
      const result = applyEvents('idle', [
        { type: 'PROCESSING_STARTED' },
        { type: 'AUDIO_CHUNK' },
        { type: 'PROCESSING_ENDED' }, // stays speaking
        { type: 'SPEAKING_ENDED' },
      ]);
      expect(result).toBe('idle');
    });

    it('chat: idle → thinking → responding → idle', () => {
      const result = applyEvents('idle', [
        { type: 'PROCESSING_STARTED' },
        { type: 'TEXT_DELTA' },
        { type: 'PROCESSING_ENDED' },
      ]);
      expect(result).toBe('idle');
    });

    it('tool use: idle → thinking → tool_calling → thinking → speaking → idle', () => {
      const result = applyEvents('idle', [
        { type: 'PROCESSING_STARTED' },
        { type: 'TOOL_UPDATE' },
        { type: 'TOOL_DONE' },
        { type: 'AUDIO_CHUNK' },
        { type: 'PROCESSING_ENDED' },
        { type: 'SPEAKING_ENDED' },
      ]);
      expect(result).toBe('idle');
    });

    it('multiple tools: thinking → tool → thinking → tool → thinking → responding', () => {
      const result = applyEvents('thinking', [
        { type: 'TOOL_UPDATE' },
        { type: 'TOOL_DONE' },
        { type: 'TOOL_UPDATE' },
        { type: 'TOOL_DONE' },
        { type: 'TEXT_DELTA' },
        { type: 'PROCESSING_ENDED' },
      ]);
      expect(result).toBe('idle');
    });

    it('voice with late audio: responding → idle → speaking → idle', () => {
      const result = applyEvents('idle', [
        { type: 'PROCESSING_STARTED' },
        { type: 'TEXT_DELTA' },
        { type: 'PROCESSING_ENDED' }, // idle — text done, audio not yet
        { type: 'AUDIO_CHUNK' }, // speaking — audio arrives late
        { type: 'SPEAKING_ENDED' },
      ]);
      expect(result).toBe('idle');
    });

    it('interrupt during speaking: speaking → interrupted → idle', () => {
      const result = applyEvents('speaking', [{ type: 'INTERRUPT' }, { type: 'PROCESSING_ENDED' }]);
      expect(result).toBe('idle');
    });

    it('error during thinking: thinking → error → idle', () => {
      const result = applyEvents('thinking', [{ type: 'ERROR' }, { type: 'PROCESSING_ENDED' }]);
      expect(result).toBe('idle');
    });
  });
});
