import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@stoa/shared': path.resolve(__dirname, '../shared'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}', 'tests/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules', 'dist'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'cobertura'],
      reportsDirectory: './coverage',
      exclude: [
        'node_modules/**',
        'dist/**',
        'src/test/**',
        '**/*.d.ts',
        '**/*.config.*',
        '**/index.ts',
        '**/*.cjs',
        'src/main.tsx',
        'src/pages/**',
        'src/components/apis/**',
        'src/components/apps/**',
        'src/components/contracts/**',
        'src/components/dashboard/**',
        'src/components/layout/**',
        'src/components/skeletons/**',
        'src/components/subscriptions/**',
        'src/components/testing/**',
        'src/components/tools/**',
        'src/components/uac/**',
        'src/components/consumers/**',
        'src/components/usage/**',
      ],
      thresholds: {
        lines: 60,
        functions: 60,
        branches: 60,
        statements: 60,
      },
    },
    reporters: ['default', 'junit'],
    outputFile: {
      junit: './junit.xml',
    },
  },
});
