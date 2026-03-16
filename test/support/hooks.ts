import {Before, After, setDefaultTimeout} from '@cucumber/cucumber';
import {chromium} from 'playwright';
import type {TankWorld} from './world';

setDefaultTimeout(60000);

const HEADLESS = process.env.HEADLESS !== 'false';

Before({tags: 'not @fake-audio'}, async function (this: TankWorld) {
    this.browser = await chromium.launch({headless: HEADLESS});
    this.context = await this.browser.newContext({
        permissions: ['microphone'],
    });

    this.page = await this.context.newPage();
});

Before({tags: '@fake-audio'}, async function (this: TankWorld) {
    this.browser = await chromium.launch({headless: HEADLESS});
    this.context = await this.browser.newContext({
        permissions: ['microphone'],
    });

    this.page = await this.context.newPage();

    // Intercept WebSocket creation so tests can send audio through it
    await this.page.addInitScript(() => {
        const OrigWebSocket = window.WebSocket;
        (window as any).WebSocket = function(url: string, protocols?: string | string[]) {
            const ws = new OrigWebSocket(url, protocols);
            // Capture the first /ws/ connection (the app's main WebSocket)
            if (url.includes('/ws/')) {
                (window as any).__testWs = ws;
            }
            return ws;
        } as any;
        (window as any).WebSocket.prototype = OrigWebSocket.prototype;
        Object.assign((window as any).WebSocket, OrigWebSocket);
    });
});

After(async function (this: TankWorld) {
    await this.page?.close();
    await this.context?.close();
    await this.browser?.close();
});
