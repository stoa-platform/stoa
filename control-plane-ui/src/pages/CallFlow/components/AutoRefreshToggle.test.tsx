import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AutoRefreshToggle } from './AutoRefreshToggle';

describe('AutoRefreshToggle', () => {
  it('renders all options', () => {
    render(<AutoRefreshToggle value={15} onChange={vi.fn()} />);
    expect(screen.getByText('Off')).toBeInTheDocument();
    expect(screen.getByText('15s')).toBeInTheDocument();
    expect(screen.getByText('30s')).toBeInTheDocument();
    expect(screen.getByText('60s')).toBeInTheDocument();
  });

  it('highlights selected option', () => {
    render(<AutoRefreshToggle value={30} onChange={vi.fn()} />);
    const btn30 = screen.getByText('30s');
    expect(btn30.className).toContain('bg-white');
  });

  it('calls onChange with correct value', () => {
    const handler = vi.fn();
    render(<AutoRefreshToggle value={15} onChange={handler} />);
    fireEvent.click(screen.getByText('60s'));
    expect(handler).toHaveBeenCalledWith(60);
  });

  it('supports off selection', () => {
    const handler = vi.fn();
    render(<AutoRefreshToggle value={15} onChange={handler} />);
    fireEvent.click(screen.getByText('Off'));
    expect(handler).toHaveBeenCalledWith(0);
  });
});
