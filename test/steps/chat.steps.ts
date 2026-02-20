import { Given, When, Then } from '@cucumber/cucumber';
import type { TankWorld } from '../support/world';
import { AppPage } from '../support/page-objects/AppPage';
import { ChatModePage } from '../support/page-objects/ChatModePage';

Given('the user switches to chat mode', async function (this: TankWorld) {
  const appPage = new AppPage(this.page);
  await appPage.clickModeToggle();
  const chatPage = new ChatModePage(this.page);
  await chatPage.input().waitFor({ state: 'visible', timeout: 5000 });
});

Given('the user switches to voice mode', async function (this: TankWorld) {
  const appPage = new AppPage(this.page);
  await appPage.clickModeToggle();
  await this.page.waitForTimeout(300);
});

Then('the empty state text {string} is visible', async function (this: TankWorld, _text: string) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.emptyState().waitFor({ state: 'visible', timeout: 5000 });
});

When('the user types {string} and sends it', async function (this: TankWorld, text: string) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.input().fill(text);
  await chatPage.sendButton().click();
});

Then('the typing indicator is visible', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.typingIndicator().waitFor({ state: 'visible', timeout: 30000 });
});

Then('eventually an assistant message appears', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.assistantMessage().waitFor({ state: 'visible', timeout: 30000 });
});

Then('the typing indicator disappears', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.typingIndicator().waitFor({ state: 'hidden', timeout: 30000 });
});

Then('the send button is disabled', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  const btn = chatPage.sendButton();
  await btn.waitFor({ state: 'visible', timeout: 5000 });
  await this.page.waitForFunction(
    () => {
      const button = document.querySelector('button[type="submit"]');
      return button?.hasAttribute('disabled');
    },
    { timeout: 30000 }
  );
});

Then('eventually the send button is enabled', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  const btn = chatPage.sendButton();
  await btn.waitFor({ state: 'visible', timeout: 5000 });
  await this.page.waitForFunction(
    () => {
      const button = document.querySelector('button[type="submit"]');
      return button && !button.hasAttribute('disabled');
    },
    { timeout: 30000 }
  );
});

Then('the chat input is visible', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.input().waitFor({ state: 'visible', timeout: 5000 });
});
