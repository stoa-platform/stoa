/** @type {import('tailwindcss').Config} */
import tokens from '../shared/tailwind/tokens.js';

export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
    // Include shared components
    '../shared/components/**/*.{js,ts,jsx,tsx}',
  ],
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
};
