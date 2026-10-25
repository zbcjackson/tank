import {When, Then} from '@cucumber/cucumber';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import type {TankWorld} from '../support/world';

const results = new WeakMap<TankWorld, string>();

async function offlinePytest(args: string[], timeout: number, requireChromium = false): Promise<string> {
  try {
    const {stdout} = await promisify(execFile)('uv', ['run', '--no-sync', 'pytest', ...args],
      {cwd: resolve(process.cwd(), '../backend'), timeout,
        env: requireChromium ? {...process.env, TANK_REQUIRE_CHROMIUM: '1'} : process.env});
    return stdout;
  } catch (error) {
    if (error instanceof Error && 'stdout' in error) {
      const killed = 'killed' in error ? String(error.killed) : 'unknown';
      error.message += `\nsubprocess killed=${killed}\n${String(error.stdout)}`;
    }
    throw error;
  }
}

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
    assert.ok(['input', 'outcomes', 'resume', 'lifecycle'].includes(contract));
    const selection = contract === 'input'
      ? 'structured_task_input or approval_binds_a_detached or invalid_task_input or assembled_task_constraints'
      : contract === 'resume'
        ? 'plugin_wait or cannot_resume_through'
        : 'structured_task_result or background_task_outcome or cleanup_failure_retains or cannot_resume_through or interruption_during_cleanup or cleanup_exception_cannot or cleanup_error_preserves_each or legacy_tool_path';
    const files = contract === 'lifecycle'
      ? ['core/tests/test_subagent.py', 'core/tests/test_task_model.py', 'core/tests/test_task_runtime.py',
        'core/tests/test_plugin_manifest.py', 'core/tests/test_model_calls.py', 'core/tests/test_decision_model.py']
      : ['core/tests/test_subagent.py'];
    const filter = contract === 'lifecycle' ? [] : ['-k', selection];
    const {stdout} = await promisify(execFile)('uv', [
      'run', '--no-sync', 'pytest', ...files, '-q', ...filter,
    ], {cwd: resolve(process.cwd(), '../backend'), timeout: 30000});
    results.set(this, stdout);
  });

Then('the plugin task contract passes without live model or desktop input',
  function (this: TankWorld) {
    assert.match(results.get(this) ?? '', /\d+ passed/);
  });

// S0 domain loop and real extension dispatch; fake UI, no paid model calls.
When('the isolated computer use host contract {string} is exercised',
  async function (this: TankWorld, contract: string) {
    assert.ok(['loop', 'plugin', 'visual', 'scoring', 'qualification', 'execution'].includes(contract));
    const file = contract === 'loop' ? 'test_ladder.py'
      : contract === 'visual' ? 'test_vision.py' : 'test_plugin.py';
    const path = contract === 'execution' ? 'core/tests/test_jev_execution.py'
      : contract === 'qualification' ? 'core/tests/test_jev_qualification.py'
      : contract === 'scoring' ? 'core/tests/test_jev_scoring.py' : `plugins/agent-computer-use/tests/${file}`;
    const filter = contract === 'execution' ? ['-k', 'execution_cli']
      : contract === 'qualification' ? ['-k', 'qualification_cli or standalone_both']
      : contract === 'scoring' ? ['-k', 'cli_is_read_only_offline'] : [];
    const stdout = await offlinePytest([path, '-q', ...filter],
      contract === 'visual' ? 45000 : 30000);
    results.set(this, stdout);
  });

Then('the computer use host contract passes without live model or desktop input',
  function (this: TankWorld) {
    assert.match(results.get(this) ?? '', /\d+ passed/);
  });

When('the isolated managed Chromium contract is exercised',
  {timeout: 135000},
  async function (this: TankWorld) {
    const stdout = await offlinePytest([
      'plugins/agent-computer-use/tests/test_dom.py', '-q',
      '-k', 'browser_config_through_real_runner or controller_native_dispatch or stop_during or runner_candidate_strategy or goal_runner or runner_advisor_returns or vision_route_real_browser or dom_freshness_ignores_native_caret or route_followup_abstention or same_origin_link or checkbox_requires or navigation_fact_and_checkbox or loading_document or finite_css_transition or continuing_animation or same_named_checkbox or uses_authored_form_names or bound_facts_cannot or name_annotation_collision or table_row_context or hidden_pseudo_animation or dom_aggregate or visible_text_limits or rendered_preformatted or explicit_candidate_budget or observe_navigation or dom_table_readback or dom_spatial',
    ], 120000, true);
    results.set(this, stdout);
  });

Then('the managed Chromium contract passes without paid model calls or personal browser access',
  function (this: TankWorld) {
    assert.match(results.get(this) ?? '', /\d+ passed/);
    assert.doesNotMatch(results.get(this) ?? '', /\d+ skipped/);
  });

When('the isolated native AX contract is exercised',
  async function (this: TankWorld) {
    const {stdout} = await promisify(execFile)('uv', [
      'run', '--no-sync', 'pytest', 'plugins/agent-computer-use/tests/test_native.py', '-q',
    ], {cwd: resolve(process.cwd(), '../backend'), timeout: 30000});
    results.set(this, stdout);
  });

Then('the native AX contract passes without real desktop input or paid model calls',
  function (this: TankWorld) {
    assert.match(results.get(this) ?? '', /\d+ passed/);
    assert.doesNotMatch(results.get(this) ?? '', /\d+ skipped/);
  });
