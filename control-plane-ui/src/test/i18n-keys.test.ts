import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, existsSync } from 'fs';
import { join, resolve } from 'path';

const ROOT = resolve(__dirname, '../..');
const LOCALES_DIR = join(ROOT, 'public', 'locales');
const BASE_LOCALE = 'en';
const NAMESPACE = 'common';

/** Flatten nested JSON to dot-notation keys */
function flattenKeys(obj: Record<string, unknown>, prefix = ''): string[] {
  const keys: string[] = [];
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      keys.push(...flattenKeys(value as Record<string, unknown>, fullKey));
    } else {
      keys.push(fullKey);
    }
  }
  return keys;
}

function loadLocaleKeys(locale: string): string[] {
  const filePath = join(LOCALES_DIR, locale, `${NAMESPACE}.json`);
  if (!existsSync(filePath)) return [];
  const data = JSON.parse(readFileSync(filePath, 'utf-8'));
  return flattenKeys(data);
}

describe('i18n locale sync', () => {
  const enKeys = loadLocaleKeys('en');
  const localeDirs = readdirSync(LOCALES_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory() && d.name !== BASE_LOCALE)
    .map((d) => d.name);

  it('en locale has keys defined', () => {
    expect(enKeys.length).toBeGreaterThan(0);
  });

  for (const locale of localeDirs) {
    it(`${locale} has all keys from en`, () => {
      const localeKeys = new Set(loadLocaleKeys(locale));
      const missing = enKeys.filter((k) => !localeKeys.has(k));
      expect(missing).toEqual([]);
    });

    it(`${locale} has no orphaned keys (not in en)`, () => {
      const enKeySet = new Set(enKeys);
      const localeKeys = loadLocaleKeys(locale);
      const orphaned = localeKeys.filter((k) => !enKeySet.has(k));
      expect(orphaned).toEqual([]);
    });
  }
});
