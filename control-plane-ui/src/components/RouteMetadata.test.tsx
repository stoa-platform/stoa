import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useNavigate } from 'react-router-dom';
import { describe, it, expect, afterEach } from 'vitest';
import i18n from 'i18next';
import { RouteMetadata } from './RouteMetadata';
import { routeTitles } from '../routeTitles';
import { config } from '../config';
import { readFileSync } from 'node:fs';

function Navigation() {
  const navigate = useNavigate();
  return <button onClick={() => navigate('/apis/tenant-example/api-example')}>API</button>;
}

afterEach(async () => {
  await act(() => i18n.changeLanguage('en'));
});

describe('RouteMetadata', () => {
  it('defines a title for every declared route pattern', () => {
    const source = readFileSync('src/App.tsx', 'utf8');
    const paths = [...source.matchAll(/<Route\s+path="([^"]+)"/g)]
      .map((match) => match[1])
      .filter((path) => !path.includes('*'));
    for (const path of paths)
      expect(
        routeTitles.some(
          ([pattern, title]) => pattern === path && title.en.trim() && title.fr.trim()
        )
      ).toBe(true);
  });
  it('updates titles on navigation without including record identifiers', async () => {
    render(
      <MemoryRouter initialEntries={['/consumers']}>
        <RouteMetadata />
        <Navigation />
      </MemoryRouter>
    );
    expect(document.title).toBe('Consumers | STOA Console');
    await userEvent.click(screen.getByRole('button', { name: 'API' }));
    expect(document.title).toBe('API Details | STOA Console');
  });

  it('follows active language on initial load and subsequent changes', async () => {
    i18n.addResourceBundle('fr', 'common', { example: 'Exemple' });
    await act(() => i18n.changeLanguage('fr'));
    render(
      <MemoryRouter>
        <RouteMetadata />
      </MemoryRouter>
    );
    expect(document.documentElement.lang).toBe('fr');
    expect(document.title).toBe('Tableau de bord | STOA Console');
    await act(() => i18n.changeLanguage('en'));
    expect(document.documentElement.lang).toBe('en');
    expect(document.title).toBe('Dashboard | STOA Console');
  });

  it('keeps English titles when i18n is disabled', async () => {
    const previous = config.features.enableI18n;
    config.features.enableI18n = false;
    await act(() => i18n.changeLanguage('fr'));
    render(
      <MemoryRouter initialEntries={['/consumers']}>
        <RouteMetadata />
      </MemoryRouter>
    );
    expect(document.documentElement.lang).toBe('en');
    expect(document.title).toBe('Consumers | STOA Console');
    config.features.enableI18n = previous;
  });
});
