#!/usr/bin/env node
/**
 * i18n key checker for Portal — scans t() calls in source files and validates
 * against locale JSON files across all namespaces.
 *
 * Checks:
 * 1. Every static t('key') in source exists in the base locale (en)
 * 2. Every key in en locale exists in all other locales (fr, etc.)
 * 3. Every key in other locales exists in en (no orphaned translations)
 *
 * Supports multiple namespaces: common, onboarding, catalog, apps, usage, workspace.
 *
 * Usage: node scripts/i18n-check.mjs [--fail-on-missing]
 *   --fail-on-missing  Exit with code 1 if any missing keys found (default: warning only)
 */

import { readFileSync, readdirSync, existsSync } from 'fs';
import { join, resolve } from 'path';

const ROOT = resolve(import.meta.dirname, '..');
const SRC_DIR = join(ROOT, 'src');
const LOCALES_DIR = join(ROOT, 'public', 'locales');
const BASE_LOCALE = 'en';
const NAMESPACES = ['common', 'onboarding', 'catalog', 'apps', 'usage', 'workspace'];

const failOnMissing = process.argv.includes('--fail-on-missing');

// -- Helpers ------------------------------------------------------------------

/** Flatten nested JSON object to dot-notation keys */
function flattenKeys(obj, prefix = '') {
  const keys = [];
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      keys.push(...flattenKeys(value, fullKey));
    } else {
      keys.push(fullKey);
    }
  }
  return keys;
}

/** Recursively collect .ts/.tsx files (excluding test/node_modules) */
function collectSourceFiles(dir) {
  const files = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '__mocks__') continue;
      files.push(...collectSourceFiles(fullPath));
    } else if (/\.(tsx?|jsx?)$/.test(entry.name) && !entry.name.includes('.test.')) {
      files.push(fullPath);
    }
  }
  return files;
}

/** Extract static t('key') and t("key") calls from source code */
function extractKeysFromSource(filePath) {
  const content = readFileSync(filePath, 'utf-8');
  const keys = new Set();
  // Match t('key.path') and t("key.path") — only static string literals
  // Also match t('ns:key.path') for namespace-prefixed keys
  const regex = /\bt\(\s*['"]([a-zA-Z][a-zA-Z0-9]*(?:[:.][ a-zA-Z][a-zA-Z0-9]*)*)['"]/g;
  let match;
  while ((match = regex.exec(content)) !== null) {
    keys.add(match[1]);
  }
  return keys;
}

/**
 * Resolve a t() key to namespace + dotPath.
 * Examples:
 *   'catalog:title' => { ns: 'catalog', key: 'title' }
 *   'nav.home'      => { ns: 'common', key: 'nav.home' }  (defaultNS)
 */
function resolveKey(rawKey) {
  const colonIdx = rawKey.indexOf(':');
  if (colonIdx > 0) {
    return { ns: rawKey.slice(0, colonIdx), key: rawKey.slice(colonIdx + 1) };
  }
  return { ns: 'common', key: rawKey };
}

// -- Main ---------------------------------------------------------------------

function main() {
  let hasErrors = false;
  let totalBaseKeys = 0;

  // 1. Load all base locale (en) namespaces
  const baseKeysByNs = new Map();
  for (const ns of NAMESPACES) {
    const filePath = join(LOCALES_DIR, BASE_LOCALE, `${ns}.json`);
    if (!existsSync(filePath)) {
      console.error(`ERROR: Base locale file not found: ${filePath}`);
      process.exit(1);
    }
    const data = JSON.parse(readFileSync(filePath, 'utf-8'));
    const keys = new Set(flattenKeys(data));
    baseKeysByNs.set(ns, keys);
    totalBaseKeys += keys.size;
  }

  // 2. Collect all t() keys from source
  const sourceFiles = collectSourceFiles(SRC_DIR);
  const usedKeys = new Map(); // rawKey => [file, ...]
  for (const file of sourceFiles) {
    const keys = extractKeysFromSource(file);
    const relPath = file.replace(ROOT + '/', '');
    for (const key of keys) {
      if (!usedKeys.has(key)) usedKeys.set(key, []);
      usedKeys.get(key).push(relPath);
    }
  }

  // 3. Check: every used key exists in base locale (correct namespace)
  const missingInBase = [];
  for (const [rawKey, files] of usedKeys) {
    const { ns, key } = resolveKey(rawKey);
    const nsKeys = baseKeysByNs.get(ns);
    if (!nsKeys || !nsKeys.has(key)) {
      missingInBase.push({ rawKey, ns, key, files });
    }
  }

  if (missingInBase.length > 0) {
    hasErrors = true;
    console.error(
      `\n${missingInBase.length} key(s) used in source but missing from ${BASE_LOCALE} locale:\n`
    );
    for (const { rawKey, ns, files } of missingInBase) {
      console.error(`  ${rawKey} (namespace: ${ns})`);
      for (const f of files) console.error(`    -> ${f}`);
    }
  }

  // 4. Check: all locales have same keys as base (per namespace)
  const localeDirs = readdirSync(LOCALES_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory() && d.name !== BASE_LOCALE)
    .map((d) => d.name);

  for (const locale of localeDirs) {
    for (const ns of NAMESPACES) {
      const localePath = join(LOCALES_DIR, locale, `${ns}.json`);
      const baseKeys = baseKeysByNs.get(ns);

      if (!existsSync(localePath)) {
        hasErrors = true;
        console.error(`\nLocale file missing: ${locale}/${ns}.json`);
        continue;
      }
      const localeData = JSON.parse(readFileSync(localePath, 'utf-8'));
      const localeKeys = new Set(flattenKeys(localeData));

      // Keys in base but missing from this locale
      const missingFromLocale = [...baseKeys].filter((k) => !localeKeys.has(k));
      if (missingFromLocale.length > 0) {
        hasErrors = true;
        console.error(
          `\n${missingFromLocale.length} key(s) in ${BASE_LOCALE}/${ns}.json but missing from ${locale}/${ns}.json:`
        );
        for (const key of missingFromLocale) {
          console.error(`  ${key}`);
        }
      }

      // Keys in this locale but not in base (orphaned)
      const orphaned = [...localeKeys].filter((k) => !baseKeys.has(k));
      if (orphaned.length > 0) {
        console.warn(
          `\n${orphaned.length} orphaned key(s) in ${locale}/${ns}.json (not in ${BASE_LOCALE}):`
        );
        for (const key of orphaned) {
          console.warn(`  ${key}`);
        }
      }
    }
  }

  // 5. Summary
  console.log(`\n-- i18n Check Summary (Portal) --`);
  console.log(`  Source files scanned: ${sourceFiles.length}`);
  console.log(`  Unique t() keys used: ${usedKeys.size}`);
  console.log(`  Namespaces: ${NAMESPACES.join(', ')}`);
  console.log(`  Base locale keys (${BASE_LOCALE}): ${totalBaseKeys}`);
  console.log(`  Locales checked: ${localeDirs.join(', ') || '(none)'}`);

  if (!hasErrors) {
    console.log(`  Status: All keys in sync\n`);
  } else {
    console.error(`  Status: Missing keys detected\n`);
    if (failOnMissing) {
      process.exit(1);
    }
  }
}

main();
