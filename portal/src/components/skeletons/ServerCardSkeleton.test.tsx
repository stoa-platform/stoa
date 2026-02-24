import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import {
  ServerCardSkeleton,
  ServerCardSkeletonGrid,
  ServerDetailSkeleton,
} from './ServerCardSkeleton';

describe('ServerCardSkeleton', () => {
  it('should render without crashing', () => {
    const { container } = render(<ServerCardSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it('should render skeleton elements', () => {
    const { container } = render(<ServerCardSkeleton />);
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('should render tag placeholders', () => {
    const { container } = render(<ServerCardSkeleton />);
    const tags = container.querySelectorAll('[class*="rounded-full"]');
    expect(tags.length).toBe(2);
  });
});

describe('ServerCardSkeletonGrid', () => {
  it('should render default 6 cards in 3 columns', () => {
    const { container } = render(<ServerCardSkeletonGrid />);
    const grid = container.querySelector('.lg\\:grid-cols-3');
    expect(grid).toBeInTheDocument();
    expect(grid?.children.length).toBe(6);
  });

  it('should render custom count of cards', () => {
    const { container } = render(<ServerCardSkeletonGrid count={4} />);
    const grid = container.firstChild;
    expect(grid?.childNodes.length).toBe(4);
  });

  it('should render 2-column grid when columns=2', () => {
    const { container } = render(<ServerCardSkeletonGrid columns={2} />);
    const grid = container.querySelector('.md\\:grid-cols-2');
    expect(grid).toBeInTheDocument();
    // Should NOT have 3-column class
    expect(container.querySelector('.lg\\:grid-cols-3')).not.toBeInTheDocument();
  });
});

describe('ServerDetailSkeleton', () => {
  it('should render without crashing', () => {
    const { container } = render(<ServerDetailSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it('should render header with icon placeholder', () => {
    const { container } = render(<ServerDetailSkeleton />);
    const icon = container.querySelector('[class*="rounded-xl"]');
    expect(icon).toBeInTheDocument();
  });

  it('should render tools section with 4 tool skeletons', () => {
    const { container } = render(<ServerDetailSkeleton />);
    const toolCards = container.querySelectorAll('.space-y-3 > div');
    expect(toolCards.length).toBe(4);
  });
});
