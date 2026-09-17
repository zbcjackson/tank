import {When, Then} from '@cucumber/cucumber';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import type {TankWorld} from '../support/world';

const results = new WeakMap<TankWorld, {status: string; cleanup?: string; started: boolean; notifications: string[]}>();

When('the isolated N2 SDK dispatch is {string}', async function (this: TankWorld, outcome: string) {
  const {stdout} = await promisify(execFile)('uv', [
    'run', '--no-sync', 'python', '../test/support/n2-sdk-dispatch.py', outcome,
  ], {cwd: resolve(process.cwd(), '../backend'), timeout: 30000});
  results.set(this, JSON.parse(stdout.trim().split('\n').at(-1)!));
});

Then('the N2 SDK worker reports {string} with confirmed cleanup', function (this: TankWorld, status: string) {
  const result = results.get(this)!;
  assert.equal(result.status, status);
  if (status === 'rejected') {
    assert.equal(result.started, false);
    assert.equal(result.notifications.length, 0);
  } else {
    assert.equal(result.cleanup, 'confirmed');
    assert.equal(result.notifications.length, 1);
  }
});
