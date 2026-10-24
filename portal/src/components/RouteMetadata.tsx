import { routeTitles } from '../routeTitles';
import { matchPath, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { DocumentMetadata } from '@stoa/shared/components/DocumentMetadata';
import { config } from '../config';

export function RouteMetadata() {
  const { pathname } = useLocation();
  const { i18n } = useTranslation();
  const title =
    routeTitles.find(([pattern]) => matchPath({ path: pattern, end: true }, pathname))?.[1] ??
    'Page';
  const language = config.features.enableI18n
    ? i18n.resolvedLanguage || i18n.language || 'en'
    : 'en';
  return <DocumentMetadata title={title + ' | STOA Portal'} language={language} />;
}
