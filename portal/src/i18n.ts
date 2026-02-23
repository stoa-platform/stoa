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

// Load initial namespaces and expose a promise that resolves when ready
const EAGER_NAMESPACES = ['common', 'onboarding', 'catalog'];
const ready: Promise<void> = (async () => {
  const loads = EAGER_NAMESPACES.map((ns) => loadNamespace(savedLanguage, ns));
  if (savedLanguage !== 'en') {
    EAGER_NAMESPACES.forEach((ns) => loads.push(loadNamespace('en', ns)));
  }
  await Promise.all(loads);
})();

export { LANGUAGE_KEY, loadNamespace, ready };
export default i18n;
