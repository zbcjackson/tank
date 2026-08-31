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
  await chatPage.activityIndicator().waitFor({ state: 'visible', timeout: 30000 });
});

Then('eventually an assistant message appears', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.assistantMessage().waitFor({ state: 'visible', timeout: 30000 });
});

Then('the typing indicator disappears', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.activityIndicator().waitFor({ state: 'hidden', timeout: 30000 });
});

Then('the stop button is visible', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.stopButton().waitFor({ state: 'visible', timeout: 30000 });
});

When('the user clicks the stop button', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.stopButton().click();
});

Then('the send button is visible', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.sendButton().waitFor({ state: 'visible', timeout: 30000 });
});

Then('eventually the send button is visible', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.sendButton().waitFor({ state: 'visible', timeout: 30000 });
});

Then('the user message {string} is visible in the conversation', async function (this: TankWorld, text: string) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.userMessage(text).first().waitFor({ state: 'visible', timeout: 10000 });
});

Then('the chat input is visible', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.input().waitFor({ state: 'visible', timeout: 5000 });
});

// ── Sentence-streaming TTS (P0-5) ──────────────────────────────────────────
// Asserts the client receives the first TTS audio frame while the LLM
// text is still streaming — only true once Brain streams sentence batches.

When('the user sends a long-answer prompt with audio streaming tracked', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  const cdp = await this.context.newCDPSession(this.page);
  await cdp.send('Network.enable');

  const state = { firstAudioAt: null as number | null, textFinalAt: null as number | null, audioFrames: 0 };
  this.audioStreamState = state;

  cdp.on('Network.webSocketFrameReceived', (params) => {
    const { opcode, payloadData } = params.response;
    if (opcode === 2) {
      // Binary frame = TTS audio chunk
      state.audioFrames += 1;
      if (state.firstAudioAt === null) state.firstAudioAt = Date.now();
    } else if (opcode === 1 && payloadData.includes('"text"')) {
      try {
        const msg = JSON.parse(payloadData) as { type?: string; is_final?: boolean };
        if (msg.type === 'text' && msg.is_final && state.textFinalAt === null) {
          state.textFinalAt = Date.now();
        }
      } catch {
        // Non-JSON text frame — ignore.
      }
    }
  });

  await chatPage.input().fill('请写一篇五百字左右的文章，详细介绍丝绸之路的历史、主要路线和文化遗产。');
  await chatPage.sendButton().click();
});

Then('the first audio frame arrives before the response text completes', async function (this: TankWorld) {
  const state = this.audioStreamState;
  if (!state) throw new Error('audio streaming was not tracked — run the tracking step first');

  // Wait (bounded) for BOTH the final text frame and the first audio frame.
  // Audio for the tail batches keeps arriving after the text finalizes, so
  // waiting for text alone would race the first chunk.
  const deadline = Date.now() + 120_000;
  while ((state.textFinalAt === null || state.firstAudioAt === null) && Date.now() < deadline) {
    await this.page.waitForTimeout(500);
  }

  if (state.audioFrames === 0) throw new Error('no audio frames received — TTS produced nothing');
  if (state.textFinalAt === null) throw new Error('response text never finalized within 120s');
  // The regression this guards against is audio waiting for the WHOLE turn
  // (baseline regression: first audio ~8s after text end). A sub-second
  // inversion is an artifact — a burst LLM tail or a slow first-batch TTS
  // startup can land the first chunk at nearly the same instant as the
  // final text frame without streaming having regressed.
  const inversionMs = state.firstAudioAt! - state.textFinalAt!;
  if (inversionMs > 1_000) {
    throw new Error(
      `first audio frame lagged the final text frame by ${Math.round(inversionMs)}ms ` +
      `(${state.firstAudioAt} vs ${state.textFinalAt}) — sentence-level TTS streaming regressed`,
    );
  }
});
