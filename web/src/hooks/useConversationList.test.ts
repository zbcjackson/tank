import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useConversationList } from './useConversationList';

vi.mock('../services/api', () => ({
  conversations: {
    list: vi.fn(),
  },
}));

import * as api from '../services/api';

const listMock = api.conversations.list as ReturnType<typeof vi.fn>;

const sampleConversation = (id: string, overrides: Partial<api.ConversationInfo> = {}) => ({
  id,
  start_time: '2026-05-28T12:00:00+00:00',
  updated_at: '2026-05-28T12:00:00+00:00',
  message_count: 2,
  preview: '',
  title: null,
  ...overrides,
});

describe('useConversationList', () => {
  beforeEach(() => {
    listMock.mockReset();
  });

  it('refresh loads conversations from the API', async () => {
    listMock.mockResolvedValueOnce([sampleConversation('a'), sampleConversation('b')]);

    const { result } = renderHook(() => useConversationList());
    expect(result.current.conversations).toEqual([]);

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.conversations).toHaveLength(2);
    expect(result.current.loading).toBe(false);
  });

  it('applyMetadataUpdate patches the matching conversation in place', async () => {
    listMock.mockResolvedValueOnce([
      sampleConversation('a'),
      sampleConversation('b'),
    ]);

    const { result } = renderHook(() => useConversationList());
    await act(async () => {
      await result.current.refresh();
    });

    act(() => {
      result.current.applyMetadataUpdate('a', { title: 'Renamed' });
    });

    await waitFor(() => {
      expect(result.current.conversations.find((c) => c.id === 'a')?.title).toBe('Renamed');
    });
    // Untouched neighbour
    expect(result.current.conversations.find((c) => c.id === 'b')?.title).toBeNull();
  });

  it('applyMetadataUpdate is a no-op when id is unknown', async () => {
    listMock.mockResolvedValueOnce([sampleConversation('a')]);

    const { result } = renderHook(() => useConversationList());
    await act(async () => {
      await result.current.refresh();
    });

    const before = result.current.conversations;

    act(() => {
      result.current.applyMetadataUpdate('missing', { title: 'X' });
    });

    expect(result.current.conversations).toBe(before);
  });

  it('records error message when refresh fails', async () => {
    listMock.mockRejectedValueOnce(new Error('network down'));

    const { result } = renderHook(() => useConversationList());
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.error).toBe('network down');
    expect(result.current.loading).toBe(false);
  });
});
