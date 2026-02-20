import type { Page, Locator } from 'playwright';

export class ChatModePage {
  constructor(private page: Page) {}

  input(): Locator {
    return this.page.locator('input[placeholder="发送消息..."]');
  }

  sendButton(): Locator {
    return this.page.locator('button[type="submit"]', { hasText: '发送' });
  }

  emptyState(): Locator {
    return this.page.locator('text=开始对话吧');
  }

  typingIndicator(): Locator {
    // The three animated dots shown when isAssistantTyping is true
    return this.page.locator('.animate-pulse').first();
  }

  assistantMessage(): Locator {
    // Assistant message content divs have animate-in class
    return this.page.locator('.animate-in').first();
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
}
