import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { Skeleton, TextSkeleton, AvatarSkeleton, ButtonSkeleton } from './Skeleton';

describe('Skeleton', () => {
  it('should render with aria-hidden', () => {
    const { container } = render(<Skeleton />);
    const el = container.firstElementChild!;
    expect(el.getAttribute('aria-hidden')).toBe('true');
  });

  it('should apply custom className', () => {
    const { container } = render(<Skeleton className="h-4 w-32" />);
    expect(container.firstElementChild!.className).toContain('h-4 w-32');
  });

  it('should include animate-pulse class', () => {
    const { container } = render(<Skeleton />);
    expect(container.firstElementChild!.className).toContain('animate-pulse');
  });
});

describe('TextSkeleton', () => {
  it('should render 3 lines by default', () => {
    const { container } = render(<TextSkeleton />);
    const lines = container.querySelectorAll('[aria-hidden="true"]');
    expect(lines).toHaveLength(3);
  });

  it('should render custom number of lines', () => {
    const { container } = render(<TextSkeleton lines={5} />);
    const lines = container.querySelectorAll('[aria-hidden="true"]');
    expect(lines).toHaveLength(5);
  });

  it('should make last line shorter', () => {
    const { container } = render(<TextSkeleton lines={2} />);
    const lines = container.querySelectorAll('[aria-hidden="true"]');
    expect(lines[0].className).toContain('w-full');
    expect(lines[1].className).toContain('w-2/3');
  });
});

describe('AvatarSkeleton', () => {
  it('should render medium size by default', () => {
    const { container } = render(<AvatarSkeleton />);
    expect(container.firstElementChild!.className).toContain('h-10 w-10');
  });

  it('should render small size', () => {
    const { container } = render(<AvatarSkeleton size="sm" />);
    expect(container.firstElementChild!.className).toContain('h-8 w-8');
  });

  it('should render large size', () => {
    const { container } = render(<AvatarSkeleton size="lg" />);
    expect(container.firstElementChild!.className).toContain('h-12 w-12');
  });

  it('should be circular', () => {
    const { container } = render(<AvatarSkeleton />);
    expect(container.firstElementChild!.className).toContain('rounded-full');
  });
});

describe('ButtonSkeleton', () => {
  it('should render medium size by default', () => {
    const { container } = render(<ButtonSkeleton />);
    expect(container.firstElementChild!.className).toContain('h-10 w-24');
  });

  it('should render small size', () => {
    const { container } = render(<ButtonSkeleton size="sm" />);
    expect(container.firstElementChild!.className).toContain('h-8 w-20');
  });

  it('should render large size', () => {
    const { container } = render(<ButtonSkeleton size="lg" />);
    expect(container.firstElementChild!.className).toContain('h-12 w-32');
  });

  it('should have rounded-lg', () => {
    const { container } = render(<ButtonSkeleton />);
    expect(container.firstElementChild!.className).toContain('rounded-lg');
  });
});
