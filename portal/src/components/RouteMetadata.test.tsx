import { readFileSync } from 'node:fs';
import { render, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, afterEach } from 'vitest';
import i18n from '../i18n';
import { config } from '../config';
import { RouteMetadata } from './RouteMetadata';
import { routeTitles } from '../routeTitles';

afterEach(async () => {
  config.features.enableI18n = true;
  await act(() => i18n.changeLanguage('en'));
});

describe('portal route titles', () => {
  it('defines a title for every declared route and the public signup page', () => {
    const source = readFileSync('src/App.tsx', 'utf8');
    const paths = [...source.matchAll(/<Route\s+path="([^"]+)"/g)]
      .map((match) => match[1])
      .filter((path) => !path.includes('*'));
    paths.push('/signup');
    for (const path of paths)
      expect(
        routeTitles.some(
          ([pattern, title]) => pattern === path && title.en.trim() && title.fr.trim()
        )
      ).toBe(true);
  });

  it('gives the sandbox a distinct title without exposing its API identifier', () => {
    render(
      <MemoryRouter initialEntries={['/apis/example/test']}>
        <RouteMetadata />
      </MemoryRouter>
    );
    expect(document.title).toBe('API Testing Sandbox | STOA Portal');
    expect(document.documentElement.lang).toBe('en');
  });

  it('uses the French title when the active language is French', async () => {
    await act(() => i18n.changeLanguage('fr'));
    render(
      <MemoryRouter initialEntries={['/apis/example/test']}>
        <RouteMetadata />
      </MemoryRouter>
    );
    expect(document.documentElement.lang).toBe('fr');
    expect(document.title).toBe("Bac à sable de test d'API | STOA Portal");
  });

  it('keeps the English title when i18n is disabled', async () => {
    config.features.enableI18n = false;
    await act(() => i18n.changeLanguage('fr'));
    render(
      <MemoryRouter initialEntries={['/apis/example/test']}>
        <RouteMetadata />
      </MemoryRouter>
    );
    expect(document.documentElement.lang).toBe('en');
    expect(document.title).toBe('API Testing Sandbox | STOA Portal');
  });
});
