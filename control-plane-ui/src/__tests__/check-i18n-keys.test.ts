/**
 * Tests for scripts/check-i18n-keys.js (CAB-1431)
 *
 * Tests the key extraction and comparison logic via child_process.spawnSync
 * against temp fixture directories.
 */

import { spawnSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { afterEach, describe, expect, test } from 'vitest';

const SCRIPT = path.resolve(__dirname, '../../scripts/check-i18n-keys.js');

// ── Test helpers ────────────────────────────────────────────────────────────

type LocaleStructure = Record<string, Record<string, unknown>>;

/**
 * Create a temporary locales directory for testing.
 * structure: { lang: { namespace: { ...keys } } }
 * Returns the tmpDir path (caller must clean up).
 */
function createTempLocales(structure: LocaleStructure): string {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'i18n-test-'));
  for (const [lang, namespaces] of Object.entries(structure)) {
    const langDir = path.join(tmpDir, lang);
    fs.mkdirSync(langDir, { recursive: true });
    for (const [ns, data] of Object.entries(namespaces)) {
      fs.writeFileSync(path.join(langDir, `${ns}.json`), JSON.stringify(data, null, 2));
    }
  }
  return tmpDir;
}

interface RunResult {
  status: number | null;
  stdout: string;
  stderr: string;
  output: string;
}

interface RunOptions {
  referenceLang?: string;
}

/**
 * Run the check script against a locales dir. Returns { status, stdout, stderr, output }.
 */
function runScript(localesDir: string, opts: RunOptions = {}): RunResult {
  const args = ['--locales-dir', localesDir];
  if (opts.referenceLang) args.push('--reference-lang', opts.referenceLang);

  const result = spawnSync('node', [SCRIPT, ...args], {
    encoding: 'utf-8',
    timeout: 10000,
  });

  return {
    status: result.status,
    stdout: result.stdout || '',
    stderr: result.stderr || '',
    output: (result.stdout || '') + (result.stderr || ''),
  };
}

// ── Tests ───────────────────────────────────────────────────────────────────

describe('check-i18n-keys', () => {
  let tmpDir: string | null = null;

  afterEach(() => {
    if (tmpDir && fs.existsSync(tmpDir)) {
      fs.rmSync(tmpDir, { recursive: true, force: true });
      tmpDir = null;
    }
  });

  describe('happy path', () => {
    test('exits 0 when all locales match reference', () => {
      tmpDir = createTempLocales({
        en: { common: { greeting: 'Hello', farewell: 'Goodbye' } },
        fr: { common: { greeting: 'Bonjour', farewell: 'Au revoir' } },
      });

      const { status } = runScript(tmpDir);
      expect(status).toBe(0);
    });

    test('exits 0 with nested keys', () => {
      tmpDir = createTempLocales({
        en: { pages: { dashboard: { title: 'Dashboard', welcome: 'Welcome' } } },
        fr: { pages: { dashboard: { title: 'Tableau de bord', welcome: 'Bienvenue' } } },
      });

      const { status } = runScript(tmpDir);
      expect(status).toBe(0);
    });

    test('exits 0 with multiple namespaces all in sync', () => {
      tmpDir = createTempLocales({
        en: {
          common: { save: 'Save', cancel: 'Cancel' },
          navigation: { home: 'Home' },
          pages: { title: 'Dashboard' },
        },
        fr: {
          common: { save: 'Enregistrer', cancel: 'Annuler' },
          navigation: { home: 'Accueil' },
          pages: { title: 'Tableau de bord' },
        },
      });

      const { status } = runScript(tmpDir);
      expect(status).toBe(0);
    });

    test('outputs OK for each namespace when in sync', () => {
      tmpDir = createTempLocales({
        en: { common: { key: 'val' } },
        fr: { common: { key: 'valeur' } },
      });

      const { output } = runScript(tmpDir);
      expect(output).toMatch(/OK.*fr\/common\.json/);
    });
  });

  describe('missing keys', () => {
    test('exits 1 when target locale is missing a key', () => {
      tmpDir = createTempLocales({
        en: { common: { greeting: 'Hello', farewell: 'Goodbye' } },
        fr: { common: { greeting: 'Bonjour' } }, // missing farewell
      });

      const { status } = runScript(tmpDir);
      expect(status).toBe(1);
    });

    test('reports the missing key name', () => {
      tmpDir = createTempLocales({
        en: { common: { actions: { save: 'Save', delete: 'Delete' } } },
        fr: { common: { actions: { save: 'Enregistrer' } } }, // missing delete
      });

      const { output } = runScript(tmpDir);
      expect(output).toMatch(/actions\.delete/);
    });

    test('reports missing count in failure message', () => {
      tmpDir = createTempLocales({
        en: { common: { a: '1', b: '2', c: '3' } },
        fr: { common: { a: 'un' } }, // missing b, c
      });

      const { output, status } = runScript(tmpDir);
      expect(status).toBe(1);
      expect(output).toMatch(/2 missing/);
    });

    test('exits 1 when entire namespace file is missing', () => {
      tmpDir = createTempLocales({
        en: { common: { key: 'val' }, pages: { title: 'Title' } },
        fr: { common: { key: 'valeur' } }, // missing pages.json
      });

      const { status, output } = runScript(tmpDir);
      expect(status).toBe(1);
      expect(output).toMatch(/MISSING FILE.*fr\/pages\.json/);
    });
  });

  describe('extra keys (warnings, not errors)', () => {
    test('exits 0 (not 1) when target has extra keys', () => {
      tmpDir = createTempLocales({
        en: { common: { greeting: 'Hello' } },
        fr: { common: { greeting: 'Bonjour', extra: 'Extra clé' } }, // extra key
      });

      const { status } = runScript(tmpDir);
      // Extra keys are warnings only, not errors
      expect(status).toBe(0);
    });

    test('shows WARN for extra keys', () => {
      tmpDir = createTempLocales({
        en: { common: { greeting: 'Hello' } },
        fr: { common: { greeting: 'Bonjour', onlyInFr: 'Seulement en FR' } },
      });

      const { output } = runScript(tmpDir);
      expect(output).toMatch(/WARN.*fr\/common\.json/);
      expect(output).toMatch(/onlyInFr/);
    });
  });

  describe('multiple languages', () => {
    test('checks all non-reference locales', () => {
      tmpDir = createTempLocales({
        en: { common: { key: 'val' } },
        fr: { common: { key: 'valeur' } },
        de: { common: { key: 'Wert' } },
      });

      const { status, output } = runScript(tmpDir);
      expect(status).toBe(0);
      expect(output).toMatch(/fr\/common\.json/);
      expect(output).toMatch(/de\/common\.json/);
    });

    test('fails if one locale is missing a key but another is complete', () => {
      tmpDir = createTempLocales({
        en: { common: { a: '1', b: '2' } },
        fr: { common: { a: 'un', b: 'deux' } }, // complete
        de: { common: { a: 'eins' } }, // missing b
      });

      const { status } = runScript(tmpDir);
      expect(status).toBe(1);
    });
  });

  describe('deeply nested keys', () => {
    test('extracts 3-level nested keys correctly', () => {
      tmpDir = createTempLocales({
        en: { pages: { dashboard: { cards: { apis: { title: 'APIs' } } } } },
        fr: { pages: { dashboard: { cards: { apis: { title: 'APIs' } } } } },
      });

      const { status } = runScript(tmpDir);
      expect(status).toBe(0);
    });

    test('reports nested missing key with dot-notation path', () => {
      tmpDir = createTempLocales({
        en: { pages: { dashboard: { cards: { apis: { title: 'APIs', desc: 'Desc' } } } } },
        fr: { pages: { dashboard: { cards: { apis: { title: 'APIs' } } } } }, // missing desc
      });

      const { output, status } = runScript(tmpDir);
      expect(status).toBe(1);
      expect(output).toMatch(/dashboard\.cards\.apis\.desc/);
    });
  });

  describe('error handling', () => {
    test('exits 1 if locales dir does not exist', () => {
      const { status } = runScript('/nonexistent/path/that/does/not/exist');
      expect(status).toBe(1);
    });

    test('exits 1 if reference lang not found', () => {
      tmpDir = createTempLocales({
        fr: { common: { key: 'val' } },
      });

      const { status } = runScript(tmpDir); // default reference is 'en', not present
      expect(status).toBe(1);
    });

    test('accepts custom reference lang', () => {
      tmpDir = createTempLocales({
        fr: { common: { key: 'val' } },
        de: { common: { key: 'Wert' } },
      });

      const { status } = runScript(tmpDir, { referenceLang: 'fr' });
      expect(status).toBe(0);
    });
  });

  describe('CI integration: real locales', () => {
    test('passes against the actual EN/FR locale files', () => {
      // This test validates the real locale files are in sync
      const realLocalesDir = path.resolve(__dirname, '../../src/i18n/locales');
      if (!fs.existsSync(realLocalesDir)) {
        // Locale files not present (e.g. branch without CAB-1429) — skip
        console.warn('Skipping real locale test: src/i18n/locales not found');
        return;
      }

      const { status, output } = runScript(realLocalesDir);
      if (status !== 0) {
        console.error('Real locale check failed:\n' + output);
      }
      expect(status).toBe(0);
    });
  });
});
