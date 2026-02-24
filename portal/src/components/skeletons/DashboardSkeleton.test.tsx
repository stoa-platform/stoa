import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { DashboardSkeleton, HomePageSkeleton } from './DashboardSkeleton';

describe('DashboardSkeleton', () => {
  it('should render without crashing', () => {
    const { container } = render(<DashboardSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it('should render stat card skeleton row', () => {
    const { container } = render(<DashboardSkeleton />);
    // StatCardSkeletonRow renders 3 stat cards
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('should render quick action placeholders', () => {
    const { container } = render(<DashboardSkeleton />);
    // Grid of 4 quick actions
    const grid = container.querySelector('.grid-cols-2');
    expect(grid).toBeInTheDocument();
  });

  it('should render activity placeholders', () => {
    const { container } = render(<DashboardSkeleton />);
    // 5 activity skeleton rows
    const spaceY = container.querySelectorAll('.space-y-3');
    expect(spaceY.length).toBeGreaterThan(0);
  });
});

describe('HomePageSkeleton', () => {
  it('should render without crashing', () => {
    const { container } = render(<HomePageSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it('should render welcome section with gradient', () => {
    const { container } = render(<HomePageSkeleton />);
    const gradient = container.querySelector('[class*="bg-gradient"]');
    expect(gradient).toBeInTheDocument();
  });

  it('should render 4 stat cards', () => {
    const { container } = render(<HomePageSkeleton />);
    const statsGrid = container.querySelector('.md\\:grid-cols-4');
    expect(statsGrid).toBeInTheDocument();
    expect(statsGrid?.children.length).toBe(4);
  });

  it('should render two-column layout for quick actions and activity', () => {
    const { container } = render(<HomePageSkeleton />);
    const twoCol = container.querySelector('.lg\\:grid-cols-2');
    expect(twoCol).toBeInTheDocument();
    expect(twoCol?.children.length).toBe(2);
  });
});
