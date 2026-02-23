#!/usr/bin/env node
/**
 * i18n key checker — scans t() calls in source files and validates against locale JSON files.
 *
 * Checks:
 * 1. Every static t('key') in source exists in the base locale (en)
 * 2. Every key in en locale exists in all other locales (fr, etc.)
 * 3. Every key in other locales exists in en (no orphaned translations)
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
const NAMESPACE = 'common';

const failOnMissing = process.argv.includes('--fail-on-missing');

// ── Helpers ──────────────────────────────────────────────────────────────────

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
  // Match t('key.path') and t("key.path") — only static string literals with dots
  const regex = /\bt\(\s*['"]([a-zA-Z][a-zA-Z0-9]*(?:\.[a-zA-Z][a-zA-Z0-9]*)+)['"]/g;
  let match;
  while ((match = regex.exec(content)) !== null) {
    keys.add(match[1]);
  }
  return keys;
}

// ── Main ─────────────────────────────────────────────────────────────────────

function main() {
  let hasErrors = false;

  // 1. Load base locale (en)
  const baseLocalePath = join(LOCALES_DIR, BASE_LOCALE, `${NAMESPACE}.json`);
  if (!existsSync(baseLocalePath)) {
    console.error(`ERROR: Base locale file not found: ${baseLocalePath}`);
    process.exit(1);
  }
  const baseLocale = JSON.parse(readFileSync(baseLocalePath, 'utf-8'));
  const baseKeys = new Set(flattenKeys(baseLocale));

  // 2. Collect all t() keys from source
  const sourceFiles = collectSourceFiles(SRC_DIR);
  const usedKeys = new Map(); // key → [file:line, ...]
  for (const file of sourceFiles) {
    const keys = extractKeysFromSource(file);
    const relPath = file.replace(ROOT + '/', '');
    for (const key of keys) {
      if (!usedKeys.has(key)) usedKeys.set(key, []);
      usedKeys.get(key).push(relPath);
    }
  }

  // 3. Check: every used key exists in base locale
  const missingInBase = [];
  for (const [key, files] of usedKeys) {
    if (!baseKeys.has(key)) {
      missingInBase.push({ key, files });
    }
  }

  if (missingInBase.length > 0) {
    hasErrors = true;
    console.error(`\n❌ ${missingInBase.length} key(s) used in source but missing from ${BASE_LOCALE}/${NAMESPACE}.json:\n`);
    for (const { key, files } of missingInBase) {
      console.error(`  ${key}`);
      for (const f of files) console.error(`    → ${f}`);
    }
  }

  // 4. Check: all locales have same keys as base
  const localeDirs = readdirSync(LOCALES_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory() && d.name !== BASE_LOCALE)
    .map((d) => d.name);

  for (const locale of localeDirs) {
    const localePath = join(LOCALES_DIR, locale, `${NAMESPACE}.json`);
    if (!existsSync(localePath)) {
      hasErrors = true;
      console.error(`\n❌ Locale file missing: ${locale}/${NAMESPACE}.json`);
      continue;
    }
    const localeData = JSON.parse(readFileSync(localePath, 'utf-8'));
    const localeKeys = new Set(flattenKeys(localeData));

    // Keys in base but missing from this locale
    const missingFromLocale = [...baseKeys].filter((k) => !localeKeys.has(k));
    if (missingFromLocale.length > 0) {
      hasErrors = true;
      console.error(`\n❌ ${missingFromLocale.length} key(s) in ${BASE_LOCALE} but missing from ${locale}:`);
      for (const key of missingFromLocale) {
        console.error(`  ${key}`);
      }
    }

    // Keys in this locale but not in base (orphaned)
    const orphaned = [...localeKeys].filter((k) => !baseKeys.has(k));
    if (orphaned.length > 0) {
      console.warn(`\n⚠️  ${orphaned.length} orphaned key(s) in ${locale} (not in ${BASE_LOCALE}):`);
      for (const key of orphaned) {
        console.warn(`  ${key}`);
      }
    }
  }

  // 5. Summary
  console.log(`\n── i18n Check Summary ──`);
  console.log(`  Source files scanned: ${sourceFiles.length}`);
  console.log(`  Unique t() keys used: ${usedKeys.size}`);
  console.log(`  Base locale keys (${BASE_LOCALE}): ${baseKeys.size}`);
  console.log(`  Locales checked: ${localeDirs.join(', ') || '(none)'}`);

  if (!hasErrors) {
    console.log(`  Status: ✅ All keys in sync\n`);
  } else {
    console.error(`  Status: ❌ Missing keys detected\n`);
    if (failOnMissing) {
      process.exit(1);
    }
  }
}

main();
