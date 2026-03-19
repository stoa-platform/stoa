import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@stoa/shared': path.resolve(__dirname, '../shared'),
      // Force shared/ components to resolve peer deps from console (not shared/node_modules)
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
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    reporters: ['default', 'junit'],
    outputFile: {
      junit: './junit.xml',
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'cobertura'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/test/**', 'src/**/*.d.ts', 'src/main.tsx'],
      thresholds: {
        lines: 63,
        functions: 52, // lowered from 53: FloatingChat+useChatService+TokenUsageWidget moved to shared/ (CAB-1836)
        branches: 56, // lowered from 57: Layout.test refactor (CAB-1884) removed duplicate "Overview" assertions
        statements: 63, // lowered from 64: Recharts migration (CAB-1885) replaced inline div bars with library calls
      },
    },
  },
});
