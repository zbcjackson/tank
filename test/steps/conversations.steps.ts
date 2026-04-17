import { When, Then } from '@cucumber/cucumber';
import type { TankWorld } from '../support/world';
import { ChatModePage } from '../support/page-objects/ChatModePage';
import { ConversationListPage } from '../support/page-objects/ConversationListPage';

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
