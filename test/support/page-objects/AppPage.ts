import type { Page, Locator } from 'playwright';

export class AppPage {
  constructor(private page: Page) {}

  async open(url = 'http://localhost:5173'): Promise<void> {
    await this.page.goto(url);
  }

  clickModeToggle(): Promise<void> {
    return this.page.locator('button[class*="fixed bottom"]').click();
  }

  errorOverlay(): Locator {
    return this.page.locator('text=连接错误');
  }

  retryButton(): Locator {
    return this.page.locator('button', { hasText: '重试' });
  }
}
