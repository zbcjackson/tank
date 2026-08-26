import { World, IWorldOptions, setWorldConstructor } from '@cucumber/cucumber';
import { Browser, BrowserContext, Page } from 'playwright';

export class TankWorld extends World {
  browser!: Browser;
  context!: BrowserContext;
  page!: Page;

  /** Set by the audio-streaming steps; undefined otherwise. */
  audioStreamState?: {
    firstAudioAt: number | null;
    textFinalAt: number | null;
    audioFrames: number;
  };

  constructor(options: IWorldOptions) {
    super(options);
  }
}

setWorldConstructor(TankWorld);
