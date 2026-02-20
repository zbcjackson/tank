import { Given, When, Then } from '@cucumber/cucumber';
import type { TankWorld } from '../support/world';
import { VoiceModePage } from '../support/page-objects/VoiceModePage';

Then('the voice mode status text is visible', async function (this: TankWorld) {
  const voicePage = new VoiceModePage(this.page);
  await voicePage.statusText().waitFor({ state: 'visible', timeout: 5000 });
});
