module.exports = {
  default: {
    requireModule: ['ts-node/register'],
    require: ['support/hooks.ts', 'steps/**/*.steps.ts'],
    paths: ['features/**/*.feature'],
    parallel: 1,
    format: ['progress-bar', 'html:reports/cucumber-report.html'],
    tags: 'not @not-implemented and not @requires-active-conversation',
  },
  // Opt-in profile for scenarios that exercise real-LLM streaming against
  // a live backend (excluded from the default run via the
  // @requires-active-conversation filter above).
  streaming: {
    requireModule: ['ts-node/register'],
    require: ['support/hooks.ts', 'steps/**/*.steps.ts'],
    paths: ['features/**/*.feature'],
    parallel: 1,
    format: ['progress-bar'],
    tags: '@streaming-audio and not @not-implemented',
  },
};
