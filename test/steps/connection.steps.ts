import { Given, Then } from '@cucumber/cucumber';
import type { TankWorld } from '../support/world';
import { AppPage } from '../support/page-objects/AppPage';
import { VoiceModePage } from '../support/page-objects/VoiceModePage';

const APP_URL = process.env.APP_URL || 'http://localhost:5173';

Given('the app is open', async function (this: TankWorld) {
  const appPage = new AppPage(this.page);
  await appPage.open(APP_URL);
  const voicePage = new VoiceModePage(this.page);
  await voicePage.statusText().filter({ hasText: '我在听，请说...' }).waitFor({ state: 'visible', timeout: 30000 });
});

Then('the status text shows {string}', async function (this: TankWorld, text: string) {
  const voicePage = new VoiceModePage(this.page);
  await voicePage.statusText().filter({ hasText: text }).waitFor({ state: 'visible', timeout: 30000 });
});
