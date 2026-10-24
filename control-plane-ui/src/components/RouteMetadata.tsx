import { routeTitleText, routeTitles } from '../routeTitles';
import { matchPath, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { DocumentMetadata } from '@stoa/shared/components/DocumentMetadata';
import { config } from '../config';

export function RouteMetadata() {
  const { pathname } = useLocation();
  const { i18n } = useTranslation();
  const language = config.features.enableI18n
    ? i18n.resolvedLanguage || i18n.language || 'en'
    : 'en';
  const title = routeTitleText(
    routeTitles.find(([pattern]) => matchPath({ path: pattern, end: true }, pathname))?.[1],
    language,
    config.features.enableI18n
  );
  return <DocumentMetadata title={title + ' | STOA Console'} language={language} />;
}
