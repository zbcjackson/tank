import { When, Then } from '@cucumber/cucumber';
import type { TankWorld } from '../support/world';
import { ChatModePage } from '../support/page-objects/ChatModePage';
import { ConversationListPage } from '../support/page-objects/ConversationListPage';
import { VoiceModePage } from '../support/page-objects/VoiceModePage';

When('the user clicks the conversations button', async function (this: TankWorld) {
  const convList = new ConversationListPage(this.page);
  await convList.conversationsButton().click();
});

Then('the conversation list sidebar is visible', async function (this: TankWorld) {
  const convList = new ConversationListPage(this.page);
  await convList.sidebar().waitFor({ state: 'visible', timeout: 5000 });
});

When('the user closes the conversation list', async function (this: TankWorld) {
  const convList = new ConversationListPage(this.page);
  await convList.closeButton().click();
});

Then('the conversation list sidebar is hidden', async function (this: TankWorld) {
  const convList = new ConversationListPage(this.page);
  await convList.sidebar().waitFor({ state: 'hidden', timeout: 5000 });
});

When('the user clicks new conversation', async function (this: TankWorld) {
  const convList = new ConversationListPage(this.page);
  await convList.newConversationButton().click();
});

Then('the conversation is empty', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.emptyState().waitFor({ state: 'visible', timeout: 5000 });
});

Then(
  'the conversation list contains at least {int} conversation(s)',
  async function (this: TankWorld, minCount: number) {
    const convList = new ConversationListPage(this.page);
    await convList
      .conversationItems()
      .first()
      .waitFor({ state: 'visible', timeout: 10000 });
    const count = await convList.conversationItems().count();
    if (count < minCount) {
      throw new Error(
        `Expected at least ${minCount} conversation(s), found ${count}`,
      );
    }
  },
);

When('the user reloads the page', async function (this: TankWorld) {
  await this.page.reload();
  const voicePage = new VoiceModePage(this.page);
  await voicePage.container().waitFor({ state: 'visible', timeout: 30000 });
});

When('the user renames the first conversation to {string}', async function (
  this: TankWorld,
  title: string,
) {
  const convList = new ConversationListPage(this.page);
  await convList.firstConversationItem().hover();
  await convList.firstRenameButton().click({ force: true });
  await convList.titleModal().waitFor({ state: 'visible', timeout: 5000 });
  await convList.titleInput().fill(title);
  await convList.titleSaveButton().click();
  await convList.titleModal().waitFor({ state: 'hidden', timeout: 5000 });
});

Then(
  'the first conversation in the list is titled {string}',
  async function (this: TankWorld, title: string) {
    const convList = new ConversationListPage(this.page);
    const item = convList.firstConversationItem();
    await item.waitFor({ state: 'visible', timeout: 10000 });
    await this.page.waitForFunction(
      ([selector, expected]) => {
        const node = document.querySelector(selector);
        return !!node && (node.textContent || '').includes(expected);
      },
      ['[data-testid="conversation-item"]', title],
      { timeout: 10000 },
    );
  },
);
