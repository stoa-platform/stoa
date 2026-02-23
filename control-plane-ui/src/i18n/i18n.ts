import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// Import translation files directly (no HTTP backend for Vite compatibility)
import enCommon from './locales/en/common.json';
import enNavigation from './locales/en/navigation.json';
import enPages from './locales/en/pages.json';
import frCommon from './locales/fr/common.json';
import frNavigation from './locales/fr/navigation.json';
import frPages from './locales/fr/pages.json';

export const defaultNS = 'common';
export const resources = {
  en: {
    common: enCommon,
    navigation: enNavigation,
    pages: enPages,
  },
  fr: {
    common: frCommon,
    navigation: frNavigation,
    pages: frPages,
  },
} as const;

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    ns: ['common', 'navigation', 'pages'],
    defaultNS,
    fallbackLng: 'en',
    supportedLngs: ['en', 'fr'],
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'stoa-language',
      caches: ['localStorage'],
    },
    interpolation: {
      escapeValue: false, // React already handles XSS
    },
    // Disable debug in production
    debug: false,
  });

export default i18n;
