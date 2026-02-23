import { useTranslation } from 'react-i18next';
import { Globe } from 'lucide-react';
import { LANGUAGE_KEY, loadNamespace } from '../i18n';

const languages = [
  { code: 'en', label: 'EN' },
  { code: 'fr', label: 'FR' },
] as const;

export function LanguageToggle() {
  const { i18n } = useTranslation();

  const handleToggle = () => {
    const next = i18n.language === 'en' ? 'fr' : 'en';
    i18n.changeLanguage(next);
    localStorage.setItem(LANGUAGE_KEY, next);
    loadNamespace(next, 'common');
  };

  const currentLabel = languages.find((l) => l.code === i18n.language)?.label || 'EN';

  return (
    <button
      onClick={handleToggle}
      className="flex items-center gap-1 px-2 py-2 text-sm text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-md transition-colors"
      aria-label={`Switch language (current: ${currentLabel})`}
    >
      <Globe className="h-4 w-4" aria-hidden="true" />
      <span className="text-xs font-medium">{currentLabel}</span>
    </button>
  );
}
