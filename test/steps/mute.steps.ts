import { When, Then } from '@cucumber/cucumber';
import type { TankWorld } from '../support/world';
import { VoiceModePage } from '../support/page-objects/VoiceModePage';

When('the user clicks the mic button', async function (this: TankWorld) {
  const voicePage = new VoiceModePage(this.page);
  await voicePage.micButton().click();
});

Then('the mic button shows muted state', async function (this: TankWorld) {
  await this.page
    .locator('[data-testid="mic-button"][data-muted="true"]')
    .waitFor({ state: 'visible', timeout: 5000 });
});

Then('the mic button shows unmuted state', async function (this: TankWorld) {
  await this.page
    .locator('[data-testid="mic-button"][data-muted="false"]')
    .waitFor({ state: 'visible', timeout: 5000 });
});
