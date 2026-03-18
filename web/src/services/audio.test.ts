import { describe, expect, it } from 'vitest';
import { AudioProcessor } from './audio';

describe('AudioProcessor', () => {
  it('can be instantiated with just an onAudio callback', () => {
    const processor = new AudioProcessor(() => {});
    expect(processor).toBeDefined();
  });
});
