import {When, Then} from '@cucumber/cucumber';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import type {TankWorld} from '../support/world';

const results = new WeakMap<TankWorld, string>();

// Reuse the actual Runner/ToolManager/SDK contracts instead of a second fake
// implementation. These isolated scenarios do not claim WebSocket coverage.
When('the isolated split desktop contract {string} is exercised',
  async function (this: TankWorld, contract: string) {
    const selection = contract === 'dispatch'
      ? 'test_runner_split_locates_current_image_and_dispatches_reference'
      : 'test_cancel_while_locating_aborts_http_and_prevents_later_calls or test_stop_during_action_validation_never_dispatches';
    assert.ok(['dispatch', 'stop'].includes(contract));
    const {stdout} = await promisify(execFile)('uv', [
      'run', '--no-sync', 'pytest', 'core/tests/test_computer_locate.py', '-q', '-k', selection,
    ], {cwd: resolve(process.cwd(), '../backend'), timeout: 30000});
    results.set(this, stdout);
  });

Then('the split desktop contract passes without live model or desktop input',
  function (this: TankWorld) {
    assert.match(results.get(this) ?? '', /\d+ passed/);
  });

// S0 generic seam coverage: real Tool → Supervisor → Runner → plugin and SQLite.
// Model/desktop boundaries are fake; this does not claim live ladder acceptance.
When('the isolated plugin task contract {string} is exercised',
  async function (this: TankWorld, contract: string) {
    assert.ok(['input', 'outcomes'].includes(contract));
    const selection = contract === 'input'
      ? 'structured_task_input or approval_binds_a_detached or invalid_task_input or assembled_task_constraints'
      : 'structured_task_result or background_task_outcome or cleanup_failure_retains or cannot_resume_through';
    const {stdout} = await promisify(execFile)('uv', [
      'run', '--no-sync', 'pytest', 'core/tests/test_subagent.py', '-q', '-k', selection,
    ], {cwd: resolve(process.cwd(), '../backend'), timeout: 30000});
    results.set(this, stdout);
  });

Then('the plugin task contract passes without live model or desktop input',
  function (this: TankWorld) {
    assert.match(results.get(this) ?? '', /\d+ passed/);
  });
