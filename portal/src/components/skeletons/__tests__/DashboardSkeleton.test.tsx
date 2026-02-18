import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { DashboardSkeleton, HomePageSkeleton } from '../DashboardSkeleton';
import { renderWithProviders } from '../../../test/helpers';

describe('DashboardSkeleton', () => {
  it('renders without crashing', () => {
    const { container } = renderWithProviders(<DashboardSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it('renders skeleton elements', () => {
    const { container } = renderWithProviders(<DashboardSkeleton />);
    const skeletonElements = container.querySelectorAll(
      '[class*="animate-pulse"], [class*="bg-gray"]'
    );
    expect(skeletonElements.length).toBeGreaterThan(0);
  });
});

describe('HomePageSkeleton', () => {
  it('renders without crashing', () => {
    const { container } = renderWithProviders(<HomePageSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it('renders a top-level container', () => {
    const { container } = renderWithProviders(<HomePageSkeleton />);
    expect(container.querySelector('.space-y-6')).toBeInTheDocument();
  });
});
