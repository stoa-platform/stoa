import { readFileSync } from 'node:fs';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import { RouteMetadata } from './RouteMetadata';
import { routeTitles } from '../routeTitles';

describe('portal route titles', () => {
  it('defines a title for every declared route and the public signup page', () => {
    const source = readFileSync('src/App.tsx', 'utf8');
    const paths = [...source.matchAll(/<Route\s+path="([^"]+)"/g)]
      .map((match) => match[1])
      .filter((path) => !path.includes('*'));
    paths.push('/signup');
    for (const path of paths)
      expect(routeTitles.some(([pattern, title]) => pattern === path && title.trim())).toBe(true);
  });

  it('gives the sandbox a distinct title without exposing its API identifier', () => {
    render(
      <MemoryRouter initialEntries={['/apis/example/test']}>
        <RouteMetadata />
      </MemoryRouter>
    );
    expect(document.title).toBe('API Testing Sandbox | STOA Portal');
  });
});
