import { When, Then } from '@cucumber/cucumber';
import type { TankWorld } from '../support/world';
import { AppPage } from '../support/page-objects/AppPage';
import { VoiceModePage } from '../support/page-objects/VoiceModePage';
import { ChatModePage } from '../support/page-objects/ChatModePage';

// Steps are shared with chat.steps.ts via Given('the user switches to chat/voice mode')
// This file handles mode-toggle-specific assertions

Then('the voice mode status text is visible after toggle', async function (this: TankWorld) {
  const voicePage = new VoiceModePage(this.page);
  await voicePage.statusText().waitFor({ state: 'visible', timeout: 5000 });
});
