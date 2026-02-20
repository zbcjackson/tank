import {Before, After, setDefaultTimeout} from '@cucumber/cucumber';
import {chromium} from 'playwright';
import type {TankWorld} from './world';

setDefaultTimeout(60000);

const APP_URL = process.env.APP_URL || 'http://localhost:5173';
const HEADLESS = process.env.HEADLESS !== 'false';


Before(async function (this: TankWorld) {
    this.browser = await chromium.launch({headless: HEADLESS});
    this.context = await this.browser.newContext({
        permissions: ['microphone'],
    });

    this.page = await this.context.newPage();
});

After(async function (this: TankWorld) {
    await this.page?.close();
    await this.context?.close();
    await this.browser?.close();
});
