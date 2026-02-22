import { describe, it, expect } from 'vitest';
import * as exports from './index';

describe('DriftDetection index exports', () => {
  it('exports DriftDetection', () => {
    expect(exports.DriftDetection).toBeDefined();
  });
});
