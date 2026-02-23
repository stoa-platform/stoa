import { useTranslation } from 'react-i18next';
import { Globe } from 'lucide-react';

const SUPPORTED_LANGUAGES = [
  { code: 'en', label: 'English', flag: '🇬🇧' },
  { code: 'fr', label: 'Français', flag: '🇫🇷' },
] as const;

type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number]['code'];

interface LanguageSwitcherProps {
  /** If true, shows only the flag icon (compact mode for header). Default: false */
  compact?: boolean;
}

export function LanguageSwitcher({ compact = false }: LanguageSwitcherProps) {
  const { i18n, t } = useTranslation();
  const currentLang = i18n.language as SupportedLanguage;
  const currentLangData =
    SUPPORTED_LANGUAGES.find((l) => l.code === currentLang) ?? SUPPORTED_LANGUAGES[0];

  function handleChange(code: string) {
    void i18n.changeLanguage(code);
  }

  if (compact) {
    return (
      <div className="relative group">
        <button
          aria-label={t('language.switchTo', { language: currentLangData.label })}
          className="flex items-center gap-1 p-2 rounded-lg text-gray-500 dark:text-neutral-400 hover:bg-gray-100 dark:hover:bg-neutral-800 transition-colors"
        >
          <Globe className="w-4 h-4" />
          <span className="text-xs font-medium uppercase">{currentLang}</span>
        </button>
        <div className="absolute right-0 top-full mt-1 w-36 bg-white dark:bg-neutral-900 border border-gray-200 dark:border-neutral-700 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
          {SUPPORTED_LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              onClick={() => handleChange(lang.code)}
              className={`w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-neutral-800 transition-colors first:rounded-t-lg last:rounded-b-lg ${
                currentLang === lang.code
                  ? 'text-blue-600 dark:text-blue-400 font-medium'
                  : 'text-gray-700 dark:text-neutral-300'
              }`}
            >
              <span>{lang.flag}</span>
              <span>{lang.label}</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {SUPPORTED_LANGUAGES.map((lang) => (
        <button
          key={lang.code}
          onClick={() => handleChange(lang.code)}
          aria-pressed={currentLang === lang.code}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            currentLang === lang.code
              ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
              : 'text-gray-600 dark:text-neutral-400 hover:bg-gray-100 dark:hover:bg-neutral-800'
          }`}
        >
          <span>{lang.flag}</span>
          <span>{lang.label}</span>
        </button>
      ))}
    </div>
  );
}
