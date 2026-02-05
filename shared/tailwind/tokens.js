/**
 * STOA Design System - Tailwind Design Tokens
 * Shared across Console UI and Portal
 *
 * Usage in tailwind.config.js:
 * const tokens = require('../shared/tailwind/tokens.js');
 * module.exports = { theme: { extend: tokens } }
 */

const colors = {
  // Primary: Teal - STOA brand identity
  primary: {
    50: '#f0fdfa',
    100: '#ccfbf1',
    200: '#99f6e4',
    300: '#5eead4',
    400: '#2dd4bf',
    500: '#14b8a6',
    600: '#0d9488',
    700: '#0f766e',
    800: '#115e59',
    900: '#134e4a',
    950: '#042f2e',
  },
  // Accent: Cyan - Secondary actions, highlights
  accent: {
    50: '#ecfeff',
    100: '#cffafe',
    200: '#a5f3fc',
    300: '#67e8f9',
    400: '#22d3ee',
    500: '#06b6d4',
    600: '#0891b2',
    700: '#0e7490',
    800: '#155e75',
    900: '#164e63',
    950: '#083344',
  },
  // Semantic colors
  success: {
    50: '#f0fdf4',
    100: '#dcfce7',
    200: '#bbf7d0',
    300: '#86efac',
    400: '#4ade80',
    500: '#22c55e',
    600: '#16a34a',
    700: '#15803d',
    800: '#166534',
    900: '#14532d',
  },
  warning: {
    50: '#fffbeb',
    100: '#fef3c7',
    200: '#fde68a',
    300: '#fcd34d',
    400: '#fbbf24',
    500: '#f59e0b',
    600: '#d97706',
    700: '#b45309',
    800: '#92400e',
    900: '#78350f',
  },
  error: {
    50: '#fef2f2',
    100: '#fee2e2',
    200: '#fecaca',
    300: '#fca5a5',
    400: '#f87171',
    500: '#ef4444',
    600: '#dc2626',
    700: '#b91c1c',
    800: '#991b1b',
    900: '#7f1d1d',
  },
  // Neutral: Gray scale for text, backgrounds, borders
  neutral: {
    50: '#fafafa',
    100: '#f5f5f5',
    200: '#e5e5e5',
    300: '#d4d4d4',
    400: '#a3a3a3',
    500: '#737373',
    600: '#525252',
    700: '#404040',
    800: '#262626',
    900: '#171717',
    950: '#0a0a0a',
  },
};

const animation = {
  // Toast slide-in animation
  'slide-in-right': 'slide-in-right 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
  'slide-out-right': 'slide-out-right 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
  // Modal scale animation
  'scale-in': 'scale-in 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
  'scale-out': 'scale-out 0.15s cubic-bezier(0.16, 1, 0.3, 1)',
  // Fade animations
  'fade-in': 'fade-in 0.2s ease-out',
  'fade-out': 'fade-out 0.15s ease-out',
};

const keyframes = {
  'slide-in-right': {
    '0%': { transform: 'translateX(100%)', opacity: '0' },
    '100%': { transform: 'translateX(0)', opacity: '1' },
  },
  'slide-out-right': {
    '0%': { transform: 'translateX(0)', opacity: '1' },
    '100%': { transform: 'translateX(100%)', opacity: '0' },
  },
  'scale-in': {
    '0%': { transform: 'scale(0.95)', opacity: '0' },
    '100%': { transform: 'scale(1)', opacity: '1' },
  },
  'scale-out': {
    '0%': { transform: 'scale(1)', opacity: '1' },
    '100%': { transform: 'scale(0.95)', opacity: '0' },
  },
  'fade-in': {
    '0%': { opacity: '0' },
    '100%': { opacity: '1' },
  },
  'fade-out': {
    '0%': { opacity: '1' },
    '100%': { opacity: '0' },
  },
};

const boxShadow = {
  'toast': '0 4px 12px rgba(0, 0, 0, 0.15)',
  'modal': '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
  'card-hover': '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
};

const borderRadius = {
  'toast': '0.75rem', // 12px
  'modal': '1rem',    // 16px
  'card': '0.75rem',  // 12px
};

const transitionTimingFunction = {
  'apple': 'cubic-bezier(0.16, 1, 0.3, 1)', // Apple's spring-like easing
};

module.exports = {
  colors,
  animation,
  keyframes,
  boxShadow,
  borderRadius,
  transitionTimingFunction,
};
