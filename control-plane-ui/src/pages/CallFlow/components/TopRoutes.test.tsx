import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TopRoutes } from './TopRoutes';
import { filterRenderableRoutes, ROUTE_LABELS_UNAVAILABLE_MESSAGE } from '../metrics';

describe('TopRoutes', () => {
  it('filters unlabelled and unknown route labels before rendering route rows', () => {
    expect(
      filterRenderableRoutes([
        { route: '(unlabelled)', p95Ms: 100, calls: 10 },
        { route: 'unknown', p95Ms: 80, calls: 8 },
        { route: '/mcp', p95Ms: 40, calls: 4 },
      ])
    ).toEqual([{ route: '/mcp', p95Ms: 40, calls: 4 }]);
  });

  it('renders an explicit unavailable state when every route label is unusable', () => {
    render(
      <TopRoutes
        routes={[
          { route: '(unlabelled)', p95Ms: 100, calls: 10 },
          { route: 'unknown', p95Ms: 80, calls: 8 },
        ]}
      />
    );

    expect(screen.getByText(ROUTE_LABELS_UNAVAILABLE_MESSAGE)).toBeInTheDocument();
  });
});
