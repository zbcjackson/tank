import { describe, expect, it } from 'vitest';
import { computeCalibrationThreshold, type CalibrationConfig } from './audio';

const cfg: CalibrationConfig = {
  durationMs: 1000,
  multiplier: 3,
  minThreshold: 0.004,
};

describe('computeCalibrationThreshold', () => {
  it('uses mean*rms multiplier when above floor', () => {
    const samples = [0.001, 0.002, 0.0015];
    const { threshold, usedFallback } = computeCalibrationThreshold(samples, cfg, 0.01);
    expect(usedFallback).toBe(false);
    expect(threshold).toBeCloseTo(0.0045, 6);
  });

  it('applies minimum floor when ambient is very low', () => {
    const samples = [0.0004, 0.0005];
    const { threshold, usedFallback } = computeCalibrationThreshold(samples, cfg, 0.01);
    expect(usedFallback).toBe(false);
    expect(threshold).toBeCloseTo(cfg.minThreshold, 6);
  });

  it('falls back to provided threshold when there are no samples', () => {
    const { threshold, usedFallback } = computeCalibrationThreshold([], cfg, 0.02);
    expect(usedFallback).toBe(true);
    expect(threshold).toBe(0.02);
  });
});

