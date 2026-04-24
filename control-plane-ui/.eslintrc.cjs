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
      // UI-2: axios must stay confined to services/http/. Everyone else goes
      // through services/api/<domain>.ts or services/api (legacy façade).
      files: ['src/**/*.ts', 'src/**/*.tsx'],
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
