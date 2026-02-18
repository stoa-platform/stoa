import { describe, it, expect } from 'vitest';
import {
  ServerCardSkeleton,
  ServerCardSkeletonGrid,
  ServerDetailSkeleton,
} from '../ServerCardSkeleton';
import { renderWithProviders } from '../../../test/helpers';

describe('ServerCardSkeleton', () => {
  it('renders without crashing', () => {
    const { container } = renderWithProviders(<ServerCardSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it('renders a card container', () => {
    const { container } = renderWithProviders(<ServerCardSkeleton />);
    expect(container.querySelector('.rounded-lg')).toBeInTheDocument();
  });
});

describe('ServerCardSkeletonGrid', () => {
  it('renders default 6 skeleton cards', () => {
    const { container } = renderWithProviders(<ServerCardSkeletonGrid />);
    const cards = container.querySelectorAll('.rounded-lg.border');
    expect(cards.length).toBe(6);
  });

  it('renders custom count of skeleton cards', () => {
    const { container } = renderWithProviders(<ServerCardSkeletonGrid count={3} />);
    const cards = container.querySelectorAll('.rounded-lg.border');
    expect(cards.length).toBe(3);
  });

  it('renders 2-column grid when columns=2', () => {
    const { container } = renderWithProviders(<ServerCardSkeletonGrid columns={2} />);
    const grid = container.firstChild as HTMLElement;
    expect(grid.className).toContain('md:grid-cols-2');
  });
});

describe('ServerDetailSkeleton', () => {
  it('renders without crashing', () => {
    const { container } = renderWithProviders(<ServerDetailSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it('renders space-y container', () => {
    const { container } = renderWithProviders(<ServerDetailSkeleton />);
    expect(container.querySelector('.space-y-6')).toBeInTheDocument();
  });
});
