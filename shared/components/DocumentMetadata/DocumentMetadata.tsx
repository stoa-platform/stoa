import { useEffect } from 'react';

export function DocumentMetadata({ title, language }: { title: string; language: string }) {
  useEffect(() => {
    document.title = title;
  }, [title]);
  useEffect(() => {
    document.documentElement.lang = language || 'en';
  }, [language]);
  return null;
}
