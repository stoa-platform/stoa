import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

const certPath = path.resolve(__dirname, 'certs/local.pem')
const keyPath = path.resolve(__dirname, 'certs/local-key.pem')
const hasLocalCerts = fs.existsSync(certPath) && fs.existsSync(keyPath)

export default defineConfig({
  plugins: [react()],
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
    https: process.env.VITE_HTTPS && hasLocalCerts ? { cert: fs.readFileSync(certPath), key: fs.readFileSync(keyPath) } : undefined,
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
})

