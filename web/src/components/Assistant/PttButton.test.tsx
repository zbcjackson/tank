import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PttButton } from './PttButton';

describe('PttButton', () => {
  it('calls onStart when clicked while not recording', () => {
    const onStart = vi.fn();
    const onStop = vi.fn();
    render(<PttButton isRecording={false} onStart={onStart} onStop={onStop} />);
    fireEvent.click(screen.getByTestId('ptt-button'));
    expect(onStart).toHaveBeenCalledOnce();
    expect(onStop).not.toHaveBeenCalled();
  });

  it('calls onStop when clicked while recording', () => {
    const onStart = vi.fn();
    const onStop = vi.fn();
    render(<PttButton isRecording={true} onStart={onStart} onStop={onStop} />);
    fireEvent.click(screen.getByTestId('ptt-button'));
    expect(onStop).toHaveBeenCalledOnce();
    expect(onStart).not.toHaveBeenCalled();
  });

  it('reflects recording state via data attribute and aria', () => {
    const { rerender } = render(
      <PttButton isRecording={false} onStart={() => {}} onStop={() => {}} />,
    );
    const button = screen.getByTestId('ptt-button');
    expect(button.getAttribute('data-recording')).toBe('false');
    expect(button.getAttribute('aria-pressed')).toBe('false');

    rerender(<PttButton isRecording={true} onStart={() => {}} onStop={() => {}} />);
    expect(button.getAttribute('data-recording')).toBe('true');
    expect(button.getAttribute('aria-pressed')).toBe('true');
  });
});
