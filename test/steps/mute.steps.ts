import { When } from '@cucumber/cucumber';
import type { TankWorld } from '../support/world';
import { VoiceModePage } from '../support/page-objects/VoiceModePage';

When('the user clicks the mic button', async function (this: TankWorld) {
  const voicePage = new VoiceModePage(this.page);
  await voicePage.micButton().click();
});
