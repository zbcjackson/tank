import type { Page, Locator } from 'playwright';

export class VoiceModePage {
  constructor(private page: Page) {}

  container(): Locator {
    return this.page.locator('[data-testid="voice-mode"]');
  }

  statusText(): Locator {
    return this.page.locator('[data-testid="voice-status"]');
  }

  wakeWordIndicator(): Locator {
    return this.page.locator('[data-testid="wake-word-indicator"]');
  }

  micButton(): Locator {
    return this.page.locator('[data-testid="mic-button"]');
  }

  stopButton(): Locator {
    return this.page.locator('[data-testid="voice-stop-button"]');
  }
}
