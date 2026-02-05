// Import shared design tokens
const tokens = require('../shared/tailwind/tokens.js');

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
    // Shared components for dark mode classes
    '../shared/components/**/*.{js,ts,jsx,tsx}',
    '../shared/contexts/**/*.{js,ts,jsx,tsx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: tokens.colors,
      animation: tokens.animation,
      keyframes: tokens.keyframes,
      boxShadow: tokens.boxShadow,
      borderRadius: tokens.borderRadius,
      transitionTimingFunction: tokens.transitionTimingFunction,
    },
  },
  plugins: [],
}
