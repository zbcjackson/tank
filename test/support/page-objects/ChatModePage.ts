import type { Page, Locator } from 'playwright';

export class ChatModePage {
  constructor(private page: Page) {}

  input(): Locator {
    return this.page.locator('[data-testid="chat-input"]');
  }

  sendButton(): Locator {
    return this.page.locator('[data-testid="send-button"]');
  }

  emptyState(): Locator {
    return this.page.locator('[data-testid="empty-state"]');
  }

  typingIndicator(): Locator {
    return this.page.locator('[data-testid="typing-indicator"]');
  }

  assistantMessage(): Locator {
    return this.page.locator('[data-testid="assistant-message"]').first();
  }

  userMessage(text: string): Locator {
    return this.page.locator(`[data-testid="user-message"]:has-text("${text}")`);
  }

  messageByContent(text: string): Locator {
    return this.page.locator(`text=${text}`);
  }

  thinkingStep(): Locator {
    return this.page.locator('[data-type="thinking"]');
  }

  toolCard(): Locator {
    return this.page.locator('[data-type="tool"]');
  }

  weatherCard(): Locator {
    return this.page.locator('[data-type="weather"]');
  }

  stopButton(): Locator {
    return this.page.locator('[data-testid="stop-button"]');
  }

  userTranscript(): Locator {
    return this.page.locator('[data-testid="user-message"]').first();
  }
}
