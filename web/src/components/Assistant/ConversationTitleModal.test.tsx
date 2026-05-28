import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ConversationTitleModal } from './ConversationTitleModal';

vi.mock('../../services/api', () => ({
  conversations: {
    updateTitle: vi.fn(),
    regenerateTitle: vi.fn(),
  },
}));

import * as api from '../../services/api';

const updateMock = api.conversations.updateTitle as ReturnType<typeof vi.fn>;
const regenerateMock = api.conversations.regenerateTitle as ReturnType<typeof vi.fn>;

describe('ConversationTitleModal', () => {
  beforeEach(() => {
    updateMock.mockReset();
    regenerateMock.mockReset();
  });

  function setup(initialTitle = 'Existing') {
    const onClose = vi.fn();
    const onSaved = vi.fn();
    render(
      <ConversationTitleModal
        conversationId="c1"
        initialTitle={initialTitle}
        onClose={onClose}
        onSaved={onSaved}
      />,
    );
    return { onClose, onSaved };
  }

  it('saves trimmed title and calls onSaved with the API response', async () => {
    updateMock.mockResolvedValueOnce({ conversation_id: 'c1', title: 'Renamed' });
    const { onSaved } = setup('');

    const input = screen.getByTestId('conversation-title-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '  Renamed  ' } });
    fireEvent.click(screen.getByTestId('conversation-title-save'));

    await waitFor(() => {
      expect(updateMock).toHaveBeenCalledWith('c1', 'Renamed');
      expect(onSaved).toHaveBeenCalledWith('Renamed');
    });
  });

  it('Save button is disabled when input is empty', () => {
    setup('');
    const saveBtn = screen.getByTestId('conversation-title-save') as HTMLButtonElement;
    expect(saveBtn.disabled).toBe(true);
  });

  it('shows error message when API call fails', async () => {
    updateMock.mockRejectedValueOnce(new Error('Server exploded'));
    setup('Some title');

    fireEvent.click(screen.getByTestId('conversation-title-save'));

    await waitFor(() => {
      expect(screen.getByTestId('conversation-title-error').textContent).toContain('Server exploded');
    });
  });

  it('Regenerate calls API and replaces the input value', async () => {
    regenerateMock.mockResolvedValueOnce({ conversation_id: 'c1', title: 'New LLM title' });
    setup('Old');

    fireEvent.click(screen.getByTestId('conversation-title-regenerate'));

    await waitFor(() => {
      expect(regenerateMock).toHaveBeenCalledWith('c1');
      const input = screen.getByTestId('conversation-title-input') as HTMLInputElement;
      expect(input.value).toBe('New LLM title');
    });
  });

  it('Regenerate empty result surfaces error message', async () => {
    regenerateMock.mockResolvedValueOnce({ conversation_id: 'c1', title: null });
    setup('Old');

    fireEvent.click(screen.getByTestId('conversation-title-regenerate'));

    await waitFor(() => {
      expect(screen.getByTestId('conversation-title-error').textContent).toContain('empty title');
    });
  });

  it('Escape key triggers onClose', () => {
    const { onClose } = setup('Old');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });
});
