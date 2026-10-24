import { readFileSync } from 'node:fs';
import { describe, it, expect } from 'vitest';
import tokens from '@stoa/shared/tailwind/tokens.js';

function luminance(hex: string) {
  const channels = hex.match(/[a-f\d]{2}/gi)!.map((value) => {
    const c = parseInt(value, 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}
function ratio(a: string, b: string) {
  const x = luminance(a),
    y = luminance(b);
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

describe('text contrast tokens', () => {
  it.each([600, 700])('keeps white text above 4.5:1 on primary-%s', (shade) => {
    expect(ratio('#ffffff', tokens.colors.primary[shade])).toBeGreaterThanOrEqual(4.5);
  });

  it.each(['portal', 'control-plane-ui'])('keeps %s muted text readable in both themes', (app) => {
    const css = readFileSync(`../${app}/src/index.css`, 'utf8');
    const values = [...css.matchAll(/--stoa-text-muted:\s*(#[\da-f]{6})/gi)].map(
      (match) => match[1]
    );
    expect(values).toHaveLength(2);
    for (const background of ['#ffffff', '#fafafa', '#f5f5f5'])
      expect(ratio(values[0], background)).toBeGreaterThanOrEqual(4.5);
    for (const background of ['#262626', '#171717'])
      expect(ratio(values[1], background)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(['portal', 'control-plane-ui'])(
    'keeps the %s focus indicator above 3:1 on light and dark surfaces',
    (app) => {
      const css = readFileSync(`../${app}/src/index.css`, 'utf8');
      const values = [...css.matchAll(/--stoa-focus:\s*(#[\da-f]{6})/gi)].map((match) => match[1]);
      expect(values).toHaveLength(2);
      for (const background of ['#ffffff', '#fafafa', '#f5f5f5'])
        expect(ratio(values[0], background)).toBeGreaterThanOrEqual(3);
      for (const background of ['#262626', '#171717'])
        expect(ratio(values[1], background)).toBeGreaterThanOrEqual(3);
    }
  );

  it('keeps primary focus outlines above 3:1 on their surfaces', () => {
    expect(ratio(tokens.colors.primary[700], '#ffffff')).toBeGreaterThanOrEqual(3);
    expect(ratio(tokens.colors.primary[300], tokens.colors.neutral[800])).toBeGreaterThanOrEqual(3);
    expect(ratio(tokens.colors.primary[300], tokens.colors.neutral[900])).toBeGreaterThanOrEqual(3);
  });

  it('keeps fixed light text readable on always-dark surfaces', () => {
    const foreground = '#a3a3a3';
    for (const background of ['#171717', '#0a0a0a', '#262626', '#1f2937'])
      expect(ratio(foreground, background)).toBeGreaterThanOrEqual(4.5);
  });
});
