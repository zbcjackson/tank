module.exports = {
  default: {
    requireModule: ['ts-node/register'],
    require: ['support/hooks.ts', 'steps/**/*.steps.ts'],
    paths: ['features/**/*.feature'],
    parallel: 1,
    format: ['progress-bar', 'html:reports/cucumber-report.html'],
  },
};
