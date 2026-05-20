import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ListenModeSettings } from './ListenModeSettings';

const baseProps = {
  listenMode: 'continuous' as const,
  voiceInterruptEnabled: false,
  wakeWordAvailable: true,
  onListenModeChange: vi.fn(),
  onVoiceInterruptEnabledChange: vi.fn(),
};

function open() {
  fireEvent.click(screen.getByTestId('listen-mode-settings-button'));
}

describe('ListenModeSettings', () => {
  it('does not render the popover when closed', () => {
    render(<ListenModeSettings {...baseProps} />);
    expect(screen.queryByTestId('listen-mode-settings-popover')).toBeNull();
  });

  it('renders three modes when wake word is available', () => {
    render(<ListenModeSettings {...baseProps} />);
    open();
    expect(screen.getByTestId('listen-mode-option-continuous')).toBeTruthy();
    expect(screen.getByTestId('listen-mode-option-wake_word')).toBeTruthy();
    expect(screen.getByTestId('listen-mode-option-ptt')).toBeTruthy();
  });

  it('hides wake_word option when wake word unavailable', () => {
    render(<ListenModeSettings {...baseProps} wakeWordAvailable={false} />);
    open();
    expect(screen.queryByTestId('listen-mode-option-wake_word')).toBeNull();
  });

  it('calls onListenModeChange when a mode is clicked', () => {
    const onListenModeChange = vi.fn();
    render(<ListenModeSettings {...baseProps} onListenModeChange={onListenModeChange} />);
    open();
    fireEvent.click(screen.getByTestId('listen-mode-option-ptt'));
    expect(onListenModeChange).toHaveBeenCalledWith('ptt');
  });

  it('shows voice-interrupt toggle only when listenMode is wake_word', () => {
    const { rerender } = render(<ListenModeSettings {...baseProps} listenMode="continuous" />);
    open();
    expect(screen.queryByTestId('voice-interrupt-toggle')).toBeNull();

    rerender(<ListenModeSettings {...baseProps} listenMode="wake_word" />);
    expect(screen.getByTestId('voice-interrupt-toggle')).toBeTruthy();
  });

  it('toggles voice-interrupt setting', () => {
    const onVoiceInterruptEnabledChange = vi.fn();
    render(
      <ListenModeSettings
        {...baseProps}
        listenMode="wake_word"
        voiceInterruptEnabled={false}
        onVoiceInterruptEnabledChange={onVoiceInterruptEnabledChange}
      />,
    );
    open();
    fireEvent.click(screen.getByTestId('voice-interrupt-toggle'));
    expect(onVoiceInterruptEnabledChange).toHaveBeenCalledWith(true);
  });
});
