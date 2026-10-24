import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { ProspectDetailModal } from './AdminProspects';
import type { ProspectDetail } from '../types';

const prospect = {
  id: 'p-1',
  email: 'ada@example.com',
  first_name: 'Ada',
  last_name: 'Lovelace',
  company: 'Analytical Engines',
  status: 'opened',
  created_at: '2026-02-01T00:00:00Z',
  expires_at: '2026-03-01T00:00:00Z',
  metrics: {
    time_to_first_tool_seconds: 0,
    tools_called_count: 0,
    pages_viewed_count: 0,
    errors_count: 0,
  },
  timeline: [],
  errors: [],
} as ProspectDetail;

describe('ProspectDetailModal title', () => {
  it('keeps a generic title while the detail is delayed, then shows the prospect', () => {
    const { rerender } = render(
      <ProspectDetailModal prospect={undefined} isLoading onClose={vi.fn()} />
    );
    const dialog = screen.getByRole('dialog', { name: 'Prospect' });
    expect(within(dialog).getByRole('heading', { name: 'Prospect' })).toHaveFocus();

    rerender(<ProspectDetailModal prospect={prospect} isLoading={false} onClose={vi.fn()} />);
    expect(screen.getByRole('dialog', { name: 'Ada Lovelace' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Ada Lovelace' })).toHaveFocus();
  });

  it('keeps the generic title when the detail fails to load', () => {
    render(<ProspectDetailModal prospect={undefined} isLoading={false} onClose={vi.fn()} />);
    const dialog = screen.getByRole('dialog', { name: 'Prospect' });
    expect(within(dialog).getByRole('heading', { name: 'Prospect' })).toHaveFocus();
    expect(screen.queryByText('ada@example.com')).not.toBeInTheDocument();
  });
});
