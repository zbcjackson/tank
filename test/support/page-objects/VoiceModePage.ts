import type { Page, Locator } from 'playwright';

export class VoiceModePage {
  constructor(private page: Page) {}

  statusText(): Locator {
    return this.page.locator('p.text-2xl');
  }

  waveform(): Locator {
    // Waveform component renders SVG or canvas inside the voice mode container
    return this.page.locator('[class*="voice"], [class*="waveform"]').first();
  }

  micButton(): Locator {
    return this.page.locator('button', { has: this.page.locator('svg') }).filter({
      hasText: '',
    }).first();
  }
}
