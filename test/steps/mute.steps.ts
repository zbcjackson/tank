import { Given, When, Then } from '@cucumber/cucumber';
import type { TankWorld } from '../support/world';
import { VoiceModePage } from '../support/page-objects/VoiceModePage';

Given('the listen mode is {string}', async function (this: TankWorld, mode: string) {
  await this.page.locator('[data-testid="listen-mode-settings-button"]').click();
  await this.page.locator(`[data-testid="listen-mode-option-${mode}"]`).click();
  // Close popover by clicking outside (below the 36px tauri drag region overlay)
  await this.page.locator('[data-testid="voice-mode"]').click({ position: { x: 5, y: 50 } });
});

When('the user clicks the mic button', async function (this: TankWorld) {
  const voicePage = new VoiceModePage(this.page);
  await voicePage.micButton().click();
});

Then('the mic button shows muted state', async function (this: TankWorld) {
  await this.page
    .locator('[data-testid="continuous-mic-button"][data-on="false"]')
    .waitFor({ state: 'visible', timeout: 5000 });
});

Then('the mic button shows unmuted state', async function (this: TankWorld) {
  await this.page
    .locator('[data-testid="continuous-mic-button"][data-on="true"]')
    .waitFor({ state: 'visible', timeout: 5000 });
});
