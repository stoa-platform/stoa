import { defineConfig, loadEnv, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';
import path from 'path';

const VERSION_ENV_KEYS = ['VITE_APP_VERSION', 'APP_VERSION'] as const;

function nonEmptyVersion(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function loadEnvWithoutBlankOverrides(
  mode: string,
  pkgDir: string,
  processEnv: Record<string, string | undefined>
): Record<string, string> {
  const saved: Partial<Record<(typeof VERSION_ENV_KEYS)[number], string | undefined>> = {};
  for (const key of VERSION_ENV_KEYS) {
    saved[key] = Object.prototype.hasOwnProperty.call(process.env, key)
      ? process.env[key]
      : undefined;
    const cleaned = nonEmptyVersion(processEnv[key]);
    if (cleaned) {
      process.env[key] = cleaned;
    } else {
      delete process.env[key];
    }
  }
  try {
    return loadEnv(mode, pkgDir, 'VITE_');
  } finally {
    for (const key of VERSION_ENV_KEYS) {
      const prev = saved[key];
      if (prev === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = prev;
      }
    }
  }
}

export interface ResolveAppVersionOptions {
  env?: Record<string, string | undefined>;
  pkgDir?: string;
}

export function resolveAppVersion(mode: string, options: ResolveAppVersionOptions = {}): string {
  const processEnv = options.env ?? process.env;
  if (processEnv.VITEST) {
    return (
      nonEmptyVersion(processEnv.VITE_APP_VERSION) ||
      nonEmptyVersion(processEnv.APP_VERSION) ||
      '0.0.0-dev'
    );
  }
  const pkgDir = options.pkgDir ?? __dirname;
  const env = loadEnvWithoutBlankOverrides(mode, pkgDir, processEnv);
  const fromEnv =
    nonEmptyVersion(processEnv.VITE_APP_VERSION) ||
    nonEmptyVersion(processEnv.APP_VERSION) ||
    nonEmptyVersion(env.VITE_APP_VERSION);
  if (fromEnv) {
    return fromEnv;
  }
  const pkg = JSON.parse(fs.readFileSync(path.resolve(pkgDir, 'package.json'), 'utf8')) as {
    version?: unknown;
  };
  return nonEmptyVersion(pkg.version) || '0.0.0-dev';
}

function writeAppVersionPlugin(version: string): Plugin {
  return {
    name: 'stoa-write-app-version',
    transformIndexHtml(html) {
      const meta = `<meta name="stoa-app-version" content="${version}" />`;
      if (!html.includes('</head>')) {
        throw new Error('index.html is missing </head>; cannot record the application version');
      }
      return html.replace('</head>', `    ${meta}\n  </head>`);
    },
    closeBundle() {
      const dist = path.resolve(__dirname, 'dist');
      fs.mkdirSync(dist, { recursive: true });
      fs.writeFileSync(path.join(dist, 'version.txt'), `${version}\n`);
    },
  };
}

const certPath = path.resolve(__dirname, 'certs/local.pem');
const keyPath = path.resolve(__dirname, 'certs/local-key.pem');
let hasLocalCerts = false;
try {
  hasLocalCerts = fs.existsSync(certPath) && fs.existsSync(keyPath);
} catch {
  /* certs dir missing — HTTP fallback */
}

export default defineConfig(({ mode }) => {
  const appVersion = resolveAppVersion(mode);
  return {
    plugins: [react(), writeAppVersionPlugin(appVersion)],
    resolve: {
      alias: {
        '@stoa/shared': path.resolve(__dirname, '../shared'),
        // Force shared/ components to resolve peer deps from portal (not shared/node_modules)
        react: path.resolve(__dirname, 'node_modules/react'),
        'react-dom': path.resolve(__dirname, 'node_modules/react-dom'),
        'react/jsx-runtime': path.resolve(__dirname, 'node_modules/react/jsx-runtime'),
        'react/jsx-dev-runtime': path.resolve(__dirname, 'node_modules/react/jsx-dev-runtime'),
        'lucide-react': path.resolve(__dirname, 'node_modules/lucide-react'),
        '@tanstack/react-query': path.resolve(__dirname, 'node_modules/@tanstack/react-query'),
        'react-i18next': path.resolve(__dirname, 'node_modules/react-i18next'),
        'react-markdown': path.resolve(__dirname, 'node_modules/react-markdown'),
      },
    },
    server: {
      port: 3001, // Different port from Console (3000)
      // HTTPS available via mkcert: set VITE_HTTPS=1 to enable (e.g. VITE_HTTPS=1 npm run dev)
      ...(process.env.VITE_HTTPS && hasLocalCerts
        ? { https: { cert: fs.readFileSync(certPath), key: fs.readFileSync(keyPath) } }
        : {}),
      allowedHosts: ['portal.stoa.local'],
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
        '/mcp': {
          target: 'http://localhost:8001',
          changeOrigin: true,
        },
      },
    },
    build: {
      // Code splitting for better caching
      rollupOptions: {
        output: {
          // Manual chunk splitting for optimal loading
          manualChunks: {
            // Vendor chunks - rarely change, cached long-term
            'vendor-react': ['react', 'react-dom', 'react-router-dom'],
            'vendor-query': ['@tanstack/react-query'],
            'vendor-auth': ['react-oidc-context', 'oidc-client-ts'],
            'vendor-utils': ['axios', 'tailwind-merge'],
          },
        },
      },
      // Improve build performance
      target: 'esnext',
      // Disable source maps in production for smaller bundles
      sourcemap: false,
      // Reduce chunk size warnings threshold
      chunkSizeWarningLimit: 500,
    },
    // Optimize dependency pre-bundling
    optimizeDeps: {
      include: ['react', 'react-dom', 'react-router-dom', '@tanstack/react-query'],
    },
    define: {
      'import.meta.env.VITE_APP_VERSION': JSON.stringify(appVersion),
    },
  };
});
