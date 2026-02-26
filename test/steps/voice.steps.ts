import { Given, When, Then } from '@cucumber/cucumber';
import type { TankWorld } from '../support/world';
import { VoiceModePage } from '../support/page-objects/VoiceModePage';

Then('the voice mode status text is visible', async function (this: TankWorld) {
  const voicePage = new VoiceModePage(this.page);
  await voicePage.statusText().waitFor({ state: 'visible', timeout: 5000 });
});

Then('the voice stop button is visible', async function (this: TankWorld) {
  const voicePage = new VoiceModePage(this.page);
  await voicePage.stopButton().waitFor({ state: 'visible', timeout: 30000 });
});

Then('eventually the status text shows {string}', async function (this: TankWorld, text: string) {
  const voicePage = new VoiceModePage(this.page);
  await voicePage.statusText().filter({ hasText: text }).waitFor({ state: 'visible', timeout: 30000 });
});
