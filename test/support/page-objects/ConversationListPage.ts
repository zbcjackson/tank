import type { Page, Locator } from 'playwright';

export class ConversationListPage {
  constructor(private page: Page) {}

  conversationsButton(): Locator {
    return this.page.locator('[data-testid="conversations-button"]');
  }

  sidebar(): Locator {
    return this.page.locator('[data-testid="conversation-list-sidebar"]');
  }

  closeButton(): Locator {
    return this.page.locator('[data-testid="close-conversation-list"]');
  }

  newConversationButton(): Locator {
    return this.page.locator('[data-testid="new-conversation-button"]');
  }

  conversationItems(): Locator {
    return this.page.locator('[data-testid="conversation-item"]');
  }

  firstConversationItem(): Locator {
    return this.page.locator('[data-testid="conversation-item"]').first();
  }

  firstRenameButton(): Locator {
    return this.page
      .locator('[data-testid="conversation-item"]')
      .first()
      .locator('[data-testid^="conversation-rename-"]');
  }

  titleModal(): Locator {
    return this.page.locator('[data-testid="conversation-title-modal"]');
  }

  titleInput(): Locator {
    return this.page.locator('[data-testid="conversation-title-input"]');
  }

  titleSaveButton(): Locator {
    return this.page.locator('[data-testid="conversation-title-save"]');
  }
}
