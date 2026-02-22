import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

const LANGUAGE_KEY = 'stoa:language';

const savedLanguage = localStorage.getItem(LANGUAGE_KEY) || 'en';

i18n.use(initReactI18next).init({
  lng: savedLanguage,
  fallbackLng: 'en',
  ns: ['common', 'onboarding', 'catalog'],
  defaultNS: 'common',
  interpolation: {
    escapeValue: false,
  },
  resources: {},
});

async function loadNamespace(lng: string, ns: string): Promise<void> {
  try {
    const response = await fetch(`/locales/${lng}/${ns}.json`);
    if (response.ok) {
      const data = await response.json();
      i18n.addResourceBundle(lng, ns, data, true, true);
    }
  } catch {
    // Silently fail — fallback language will be used
  }
}

// Load initial namespaces
const EAGER_NAMESPACES = ['common', 'onboarding', 'catalog'];
EAGER_NAMESPACES.forEach((ns) => {
  loadNamespace(savedLanguage, ns);
  if (savedLanguage !== 'en') loadNamespace('en', ns);
});

export { LANGUAGE_KEY, loadNamespace };
export default i18n;
