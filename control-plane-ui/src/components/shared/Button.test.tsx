import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { createRef } from 'react';
import { Button } from '@stoa/shared/components/Button';

describe('Button', () => {
  it('renders with default props (primary, md)', () => {
    render(<Button>Click me</Button>);
    const btn = screen.getByRole('button', { name: 'Click me' });
    expect(btn).toBeInTheDocument();
    expect(btn.className).toContain('bg-primary-600');
    expect(btn.className).toContain('px-4');
    expect(btn.className).toContain('text-sm');
  });

  it.each([
    ['primary', 'bg-primary-600'],
    ['secondary', 'border-neutral-300'],
    ['danger', 'bg-error-600'],
    ['ghost', 'hover:bg-neutral-100'],
    ['link', 'hover:underline'],
  ] as const)('renders %s variant with correct classes', (variant, expectedClass) => {
    render(<Button variant={variant}>Test</Button>);
    const btn = screen.getByRole('button');
    expect(btn.className).toContain(expectedClass);
  });

  it.each([
    ['sm', 'px-3', 'text-xs'],
    ['md', 'px-4', 'text-sm'],
    ['lg', 'px-5', 'text-base'],
  ] as const)('renders %s size with correct classes', (size, expectedPadding, expectedText) => {
    render(<Button size={size}>Test</Button>);
    const btn = screen.getByRole('button');
    expect(btn.className).toContain(expectedPadding);
    expect(btn.className).toContain(expectedText);
  });

  it('shows spinner and disables button when loading', () => {
    render(<Button loading>Save</Button>);
    const btn = screen.getByRole('button');
    expect(btn).toBeDisabled();
    expect(btn.querySelector('svg.animate-spin')).toBeInTheDocument();
  });

  it('renders icon on the left by default', () => {
    const icon = <span data-testid="test-icon">+</span>;
    render(<Button icon={icon}>Add</Button>);
    const btn = screen.getByRole('button');
    const iconEl = screen.getByTestId('test-icon');
    expect(btn).toContainElement(iconEl);
    const children = Array.from(btn.childNodes);
    const iconIndex = children.indexOf(iconEl);
    const textIndex = children.findIndex((n) => n.textContent === 'Add');
    expect(iconIndex).toBeLessThan(textIndex);
  });

  it('renders icon on the right when iconPosition="right"', () => {
    const icon = <span data-testid="test-icon">+</span>;
    render(
      <Button icon={icon} iconPosition="right">
        Add
      </Button>
    );
    const btn = screen.getByRole('button');
    const children = Array.from(btn.childNodes);
    const iconIndex = children.indexOf(screen.getByTestId('test-icon'));
    const textIndex = children.findIndex((n) => n.textContent === 'Add');
    expect(iconIndex).toBeGreaterThan(textIndex);
  });

  it('applies w-full when fullWidth is true', () => {
    render(<Button fullWidth>Wide</Button>);
    expect(screen.getByRole('button').className).toContain('w-full');
  });

  it('forwards ref and native button props', async () => {
    const ref = createRef<HTMLButtonElement>();
    const onClick = vi.fn();
    render(
      <Button ref={ref} onClick={onClick} type="submit">
        Submit
      </Button>
    );
    const btn = screen.getByRole('button');
    expect(ref.current).toBe(btn);
    expect(btn).toHaveAttribute('type', 'submit');
    await userEvent.click(btn);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('link variant has no size padding classes', () => {
    render(<Button variant="link">Learn more</Button>);
    const btn = screen.getByRole('button');
    expect(btn.className).not.toContain('px-4');
    expect(btn.className).not.toContain('py-2.5');
  });

  it('applies disabled:opacity-50 when disabled', () => {
    render(<Button disabled>Disabled</Button>);
    const btn = screen.getByRole('button');
    expect(btn).toBeDisabled();
    expect(btn.className).toContain('disabled:opacity-50');
  });
});
