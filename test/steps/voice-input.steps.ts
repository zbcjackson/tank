import fs from 'fs';
import path from 'path';
import { When, Then } from '@cucumber/cucumber';
import type { TankWorld } from '../support/world';
import { ChatModePage } from '../support/page-objects/ChatModePage';

const FIXTURE_DIR = path.resolve(__dirname, '..', 'fixtures', 'audio');

When('the WAV fixture {string} is sent over the WebSocket', async function (this: TankWorld, filename: string) {
  const wavPath = path.join(FIXTURE_DIR, filename);
  const wavBuffer = fs.readFileSync(wavPath);

  // Skip WAV header (44 bytes) to get raw Int16 PCM data
  const pcmBuffer = wavBuffer.subarray(44);
  const pcmBase64 = pcmBuffer.toString('base64');

  // Wait for the intercepted WebSocket to be open
  await this.page.waitForFunction(
    () => (window as any).__testWs?.readyState === WebSocket.OPEN,
    { timeout: 10000 },
  );

  // Send PCM as Int16 binary chunks (1600 samples = 100ms at 16kHz)
  const CHUNK_BYTES = 1600 * 2;

  await this.page.evaluate(
    ({ pcmBase64, chunkBytes, chunkIntervalMs }) => {
      return new Promise<void>((resolve) => {
        const raw = Uint8Array.from(atob(pcmBase64), (c) => c.charCodeAt(0));
        const ws = (window as any).__testWs as WebSocket;

        let offset = 0;
        let sent = 0;
        const timer = setInterval(() => {
          if (offset >= raw.length) {
            clearInterval(timer);
            resolve();
            return;
          }
          const end = Math.min(offset + chunkBytes, raw.length);
          const chunk = raw.slice(offset, end);
          ws.send(chunk.buffer);
          offset = end;
          sent++;
        }, chunkIntervalMs);
      });
    },
    { pcmBase64, chunkBytes: CHUNK_BYTES, chunkIntervalMs: 100 },
  );

  // Wait for backend ASR to process (needs silence after speech to detect endpoint)
  await this.page.waitForTimeout(3000);
});

Then('eventually a user transcript appears in the conversation', async function (this: TankWorld) {
  const chatPage = new ChatModePage(this.page);
  await chatPage.userTranscript().waitFor({ state: 'visible', timeout: 30000 });
});
