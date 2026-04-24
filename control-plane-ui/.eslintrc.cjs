module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', '.eslintrc.cjs'],
  parser: '@typescript-eslint/parser',
  plugins: ['react-refresh'],
  rules: {
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' }],
  },
  overrides: [
    {
      files: ['**/*.test.ts', '**/*.test.tsx'],
      rules: {
        '@typescript-eslint/no-explicit-any': 'off',
      },
    },
    {
      // UI-2: consumer-code import hygiene.
      //
      // (1) axios (UI-2 bonus): must stay confined to services/http/.
      //     Everyone else goes through services/api/<domain>.ts or
      //     services/api (legacy façade).
      //
      // (2) services/http/{auth,refresh,interceptors} (UI-2 P2-7): internals
      //     private to services/http/** and the services/api.ts façade.
      //     Consumer code must use apiService for auth state mutations.
      //
      // services/http/** itself is whitelisted via excludedFiles; tests and
      // services/api.ts get a looser variant in the next override below.
      files: ['src/**/*.ts', 'src/**/*.tsx'],
      excludedFiles: [
        'src/services/http/**',
        'src/services/api.ts',
        'src/__tests__/**',
        'src/test/**',
        '**/*.test.ts',
        '**/*.test.tsx',
      ],
      rules: {
        'no-restricted-imports': [
          'error',
          {
            paths: [
              {
                name: 'axios',
                message:
                  'Import httpClient from services/http (or a domain client from services/api/<domain>). Direct axios use is confined to services/http/.',
              },
            ],
            patterns: [
              {
                group: [
                  '@/services/http/auth',
                  '@/services/http/refresh',
                  '@/services/http/interceptors',
                  '*/services/http/auth',
                  '*/services/http/refresh',
                  '*/services/http/interceptors',
                ],
                message:
                  'HTTP auth internals are private to services/http/**. Use apiService façade (services/api.ts) for auth state mutations.',
              },
            ],
          },
        ],
      },
    },
    {
      // UI-2 P2-7 bis: tests outside services/http/ and the services/api.ts
      // façade can touch HTTP auth internals directly (canary regression
      // coverage + façade delegation), but they still get the axios ban.
      // Tests INSIDE services/http/ are exempt from both rules — they need
      // to drive a real axios instance through the interceptors.
      files: [
        'src/services/api.ts',
        'src/__tests__/**/*.ts',
        'src/__tests__/**/*.tsx',
        'src/test/**/*.ts',
        'src/test/**/*.tsx',
        'src/**/*.test.ts',
        'src/**/*.test.tsx',
      ],
      excludedFiles: ['src/services/http/**'],
      rules: {
        'no-restricted-imports': [
          'error',
          {
            paths: [
              {
                name: 'axios',
                message:
                  'Import httpClient from services/http (or a domain client from services/api/<domain>). Direct axios use is confined to services/http/.',
              },
            ],
          },
        ],
      },
    },
    {
      // UI-2 P0-7: hooks that make authenticated HTTP calls must route through
      // httpClient so the refresh interceptor handles 401s. Legitimate
      // unauthenticated use (health probes, cross-origin no-cors) requires
      // an explicit eslint-disable-next-line with justification.
      files: ['src/hooks/**/*.ts', 'src/hooks/**/*.tsx'],
      rules: {
        'no-restricted-globals': [
          'error',
          {
            name: 'fetch',
            message:
              'Use httpClient from services/http for authenticated requests. If legitimate unauthenticated usage (health probes), add eslint-disable-next-line with justification.',
          },
        ],
      },
    },
  ],
}
