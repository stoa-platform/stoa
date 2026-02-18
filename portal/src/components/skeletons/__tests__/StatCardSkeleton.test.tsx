import { describe, it, expect } from 'vitest';
import {
  StatCardSkeleton,
  StatCardSkeletonRow,
  StatCardWithIconSkeleton,
  UsageStatSkeleton,
} from '../StatCardSkeleton';
import { renderWithProviders } from '../../../test/helpers';

describe('StatCardSkeleton', () => {
  it('renders without crashing', () => {
    const { container } = renderWithProviders(<StatCardSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it('renders a card container with border', () => {
    const { container } = renderWithProviders(<StatCardSkeleton />);
    expect(container.querySelector('.rounded-lg.border')).toBeInTheDocument();
  });
});

describe('StatCardSkeletonRow', () => {
  it('renders default 3 cards', () => {
    const { container } = renderWithProviders(<StatCardSkeletonRow />);
    const cards = container.querySelectorAll('.rounded-lg.border');
    expect(cards.length).toBe(3);
  });

  it('renders custom count of cards', () => {
    const { container } = renderWithProviders(<StatCardSkeletonRow count={4} />);
    const cards = container.querySelectorAll('.rounded-lg.border');
    expect(cards.length).toBe(4);
  });
});

describe('StatCardWithIconSkeleton', () => {
  it('renders without crashing', () => {
    const { container } = renderWithProviders(<StatCardWithIconSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });
});

describe('UsageStatSkeleton', () => {
  it('renders without crashing', () => {
    const { container } = renderWithProviders(<UsageStatSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });
});
