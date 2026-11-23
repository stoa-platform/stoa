// @vitest-environment node
import fs from 'fs';
import os from 'os';
import path from 'path';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { resolveAppVersion } from '../vite.config';

function withTempProject(files: Record<string, string>, fn: (dir: string) => void): void {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'console-vite-env-'));
  try {
    for (const [name, content] of Object.entries(files)) {
      fs.writeFileSync(path.join(dir, name), content, 'utf8');
    }
    fn(dir);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('vite resolveAppVersion with real loadEnv', () => {
  it('reads VITE_APP_VERSION from .env when process.env.VITE_APP_VERSION is empty', () => {
    vi.stubEnv('VITEST', '');
    vi.stubEnv('VITE_APP_VERSION', '');
    vi.stubEnv('APP_VERSION', '');

    withTempProject(
      {
        '.env': 'VITE_APP_VERSION=2.5.0\n',
        'package.json': JSON.stringify({ version: '1.13.0' }),
      },
      (pkgDir) => {
        expect(resolveAppVersion('production', { pkgDir })).toBe('2.5.0');
        expect(process.env.VITE_APP_VERSION).toBe('');
        expect(process.env.APP_VERSION).toBe('');
      }
    );
  });

  it('reads VITE_APP_VERSION from .env when process.env.VITE_APP_VERSION is whitespace', () => {
    vi.stubEnv('VITEST', '');
    vi.stubEnv('VITE_APP_VERSION', '   \t ');
    vi.stubEnv('APP_VERSION', '  ');

    withTempProject(
      {
        '.env': 'VITE_APP_VERSION= 2.6.0-rc.1 \n',
        'package.json': JSON.stringify({ version: '1.13.0' }),
      },
      (pkgDir) => {
        expect(resolveAppVersion('production', { pkgDir })).toBe('2.6.0-rc.1');
        expect(process.env.VITE_APP_VERSION).toBe('   \t ');
        expect(process.env.APP_VERSION).toBe('  ');
      }
    );
  });

  it('prefers non-empty process.env overrides over .env', () => {
    vi.stubEnv('VITEST', '');
    vi.stubEnv('VITE_APP_VERSION', ' 3.0.0 ');
    vi.stubEnv('APP_VERSION', '2.9.0');

    withTempProject(
      {
        '.env': 'VITE_APP_VERSION=2.5.0\n',
        'package.json': JSON.stringify({ version: '1.13.0' }),
      },
      (pkgDir) => {
        expect(resolveAppVersion('production', { pkgDir })).toBe('3.0.0');
      }
    );
  });

  it('uses process.env.APP_VERSION when VITE_APP_VERSION is blank in process.env', () => {
    vi.stubEnv('VITEST', '');
    vi.stubEnv('VITE_APP_VERSION', '   ');
    vi.stubEnv('APP_VERSION', ' 2.8.0 ');

    withTempProject(
      {
        '.env': 'VITE_APP_VERSION=2.5.0\n',
        'package.json': JSON.stringify({ version: '1.13.0' }),
      },
      (pkgDir) => {
        expect(resolveAppVersion('production', { pkgDir })).toBe('2.8.0');
      }
    );
  });

  it('falls back to package.json and then 0.0.0-dev when process.env and .env are blank', () => {
    vi.stubEnv('VITEST', '');
    vi.stubEnv('VITE_APP_VERSION', '  ');
    vi.stubEnv('APP_VERSION', '');

    withTempProject(
      {
        '.env': 'VITE_APP_VERSION=   \n',
        'package.json': JSON.stringify({ version: ' 1.13.0 ' }),
      },
      (pkgDir) => {
        expect(resolveAppVersion('production', { pkgDir })).toBe('1.13.0');
      }
    );

    withTempProject(
      {
        '.env': 'VITE_APP_VERSION=   \n',
        'package.json': JSON.stringify({ version: '   ' }),
      },
      (pkgDir) => {
        expect(resolveAppVersion('production', { pkgDir })).toBe('0.0.0-dev');
      }
    );
  });

  it('isolates options.env from blank or set process.env values during real loadEnv', () => {
    vi.stubEnv('VITE_APP_VERSION', '9.9.9');
    vi.stubEnv('APP_VERSION', '8.8.8');

    withTempProject(
      {
        '.env': 'VITE_APP_VERSION=2.7.0\n',
        'package.json': JSON.stringify({ version: '1.13.0' }),
      },
      (pkgDir) => {
        expect(
          resolveAppVersion('production', {
            env: { VITE_APP_VERSION: '   ', APP_VERSION: '' },
            pkgDir,
          })
        ).toBe('2.7.0');
        expect(process.env.VITE_APP_VERSION).toBe('9.9.9');
        expect(process.env.APP_VERSION).toBe('8.8.8');
      }
    );
  });
});
