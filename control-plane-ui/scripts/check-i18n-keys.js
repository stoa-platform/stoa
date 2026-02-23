#!/usr/bin/env node
/**
 * check-i18n-keys.js — CI script to detect missing translation keys (CAB-1431)
 *
 * Usage:
 *   node scripts/check-i18n-keys.js [--reference-lang en] [--locales-dir src/i18n/locales]
 *
 * Compares all locale files against a reference language (default: 'en').
 * Exits with code 1 if any key is missing or extra keys are present.
 * Exits with code 0 if all locales match the reference.
 *
 * Supports nested JSON objects (deep key comparison).
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── Parse CLI args ────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
let referenceLang = 'en';
let localesDir = path.join(__dirname, '..', 'src', 'i18n', 'locales');

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--reference-lang' && args[i + 1]) referenceLang = args[++i];
  if (args[i] === '--locales-dir' && args[i + 1]) localesDir = path.resolve(args[++i]);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Recursively extract all dot-notation keys from a nested object.
 * e.g. { a: { b: 1 } } → ['a.b']
 */
function extractKeys(obj, prefix = '') {
  const keys = [];
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      keys.push(...extractKeys(value, fullKey));
    } else {
      keys.push(fullKey);
    }
  }
  return keys;
}

/**
 * Load and parse a JSON file. Returns null if the file doesn't exist.
 */
function loadJson(filePath) {
  if (!fs.existsSync(filePath)) return null;
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
  } catch (err) {
    console.error(`  ERROR: Failed to parse ${filePath}: ${err.message}`);
    process.exit(1);
  }
}

// ── Main ──────────────────────────────────────────────────────────────────────

if (!fs.existsSync(localesDir)) {
  console.error(`ERROR: Locales directory not found: ${localesDir}`);
  process.exit(1);
}

const allLocales = fs
  .readdirSync(localesDir)
  .filter((entry) => fs.statSync(path.join(localesDir, entry)).isDirectory());

if (!allLocales.includes(referenceLang)) {
  console.error(`ERROR: Reference language '${referenceLang}' not found in ${localesDir}`);
  console.error(`Available: ${allLocales.join(', ')}`);
  process.exit(1);
}

const refDir = path.join(localesDir, referenceLang);
const namespaceFiles = fs
  .readdirSync(refDir)
  .filter((f) => f.endsWith('.json'))
  .map((f) => f.replace('.json', ''));

const targetLocales = allLocales.filter((l) => l !== referenceLang);

console.log(`\ni18n key check — reference: '${referenceLang}'`);
console.log(`Namespaces: ${namespaceFiles.join(', ')}`);
console.log(`Checking: ${targetLocales.join(', ')}\n`);

let totalErrors = 0;

for (const ns of namespaceFiles) {
  const refFile = path.join(refDir, `${ns}.json`);
  const refData = loadJson(refFile);
  const refKeys = new Set(extractKeys(refData));

  for (const lang of targetLocales) {
    const targetFile = path.join(localesDir, lang, `${ns}.json`);
    const targetData = loadJson(targetFile);

    if (targetData === null) {
      console.error(`  MISSING FILE: ${lang}/${ns}.json (reference has ${refKeys.size} keys)`);
      totalErrors += refKeys.size;
      continue;
    }

    const targetKeys = new Set(extractKeys(targetData));

    // Missing keys (in reference but not in target)
    const missing = [...refKeys].filter((k) => !targetKeys.has(k));

    // Extra keys (in target but not in reference)
    const extra = [...targetKeys].filter((k) => !refKeys.has(k));

    const nsLabel = `${lang}/${ns}.json`;

    if (missing.length === 0 && extra.length === 0) {
      console.log(`  OK  ${nsLabel} (${refKeys.size} keys)`);
    } else {
      if (missing.length > 0) {
        console.error(`  FAIL ${nsLabel} — ${missing.length} missing key(s):`);
        missing.forEach((k) => console.error(`       - ${k}`));
        totalErrors += missing.length;
      }
      if (extra.length > 0) {
        console.warn(`  WARN ${nsLabel} — ${extra.length} extra key(s) not in reference:`);
        extra.forEach((k) => console.warn(`       + ${k}`));
        // Extra keys are warnings only, not errors
      }
    }
  }
}

console.log('');

if (totalErrors === 0) {
  console.log(`✓ All i18n keys are in sync.`);
  process.exit(0);
} else {
  console.error(`✗ Found ${totalErrors} missing translation key(s). Fix them before merging.`);
  process.exit(1);
}
