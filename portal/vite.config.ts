import { defineConfig, loadEnv, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

function resolveAppVersion(mode: string): string {
  if (process.env.VITEST) {
    return process.env.VITE_APP_VERSION || '0.0.0-dev'
  }
  const env = loadEnv(mode, __dirname, 'VITE_')
  const pkg = JSON.parse(fs.readFileSync(path.resolve(__dirname, 'package.json'), 'utf8')) as {
    version?: string
  }
  return process.env.VITE_APP_VERSION || env.VITE_APP_VERSION || pkg.version || '0.0.0-dev'
}

function writeAppVersionPlugin(version: string): Plugin {
  return {
    name: 'stoa-write-app-version',
    transformIndexHtml(html) {
      const meta = `<meta name="stoa-app-version" content="${version}" />`
      if (!html.includes('</head>')) {
        throw new Error('index.html is missing </head>; cannot record the application version')
      }
      return html.replace('</head>', `    ${meta}\n  </head>`)
    },
    closeBundle() {
      const dist = path.resolve(__dirname, 'dist')
      fs.mkdirSync(dist, { recursive: true })
      fs.writeFileSync(path.join(dist, 'version.txt'), `${version}\n`)
    },
  }
}

const certPath = path.resolve(__dirname, 'certs/local.pem')
const keyPath = path.resolve(__dirname, 'certs/local-key.pem')
let hasLocalCerts = false
try { hasLocalCerts = fs.existsSync(certPath) && fs.existsSync(keyPath) } catch { /* certs dir missing — HTTP fallback */ }

export default defineConfig(({ mode }) => {
  const appVersion = resolveAppVersion(mode)
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
    ...(process.env.VITE_HTTPS && hasLocalCerts ? { https: { cert: fs.readFileSync(certPath), key: fs.readFileSync(keyPath) } } : {}),
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
  }
})
