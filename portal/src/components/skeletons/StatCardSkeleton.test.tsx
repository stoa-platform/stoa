import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import {
  StatCardSkeleton,
  StatCardSkeletonRow,
  StatCardWithIconSkeleton,
  UsageStatSkeleton,
} from './StatCardSkeleton';

describe('StatCardSkeleton', () => {
  it('should render without crashing', () => {
    const { container } = render(<StatCardSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it('should render skeleton pulse elements', () => {
    const { container } = render(<StatCardSkeleton />);
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });
});

describe('StatCardSkeletonRow', () => {
  it('should render default 3 stat cards', () => {
    const { container } = render(<StatCardSkeletonRow />);
    const grid = container.querySelector('.md\\:grid-cols-3');
    expect(grid).toBeInTheDocument();
    expect(grid?.children.length).toBe(3);
  });

  it('should render custom count', () => {
    const { container } = render(<StatCardSkeletonRow count={5} />);
    const grid = container.firstChild;
    expect(grid?.childNodes.length).toBe(5);
  });
});

describe('StatCardWithIconSkeleton', () => {
  it('should render without crashing', () => {
    const { container } = render(<StatCardWithIconSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it('should render icon placeholder', () => {
    const { container } = render(<StatCardWithIconSkeleton />);
    const iconPlaceholder = container.querySelector('[class*="rounded-lg"]');
    expect(iconPlaceholder).toBeInTheDocument();
  });
});

describe('UsageStatSkeleton', () => {
  it('should render without crashing', () => {
    const { container } = render(<UsageStatSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it('should render 3-column stats grid', () => {
    const { container } = render(<UsageStatSkeleton />);
    const statsGrid = container.querySelector('.grid-cols-3');
    expect(statsGrid).toBeInTheDocument();
    expect(statsGrid?.children.length).toBe(3);
  });

  it('should render icon and text placeholders', () => {
    const { container } = render(<UsageStatSkeleton />);
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });
});
