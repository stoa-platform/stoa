/**
 * Tests for ConsumerCard component (CAB-1121)
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ConsumerCard } from './ConsumerCard';
import type { Consumer } from '../../types';

const mockConsumer: Consumer = {
  id: 'c1',
  name: 'ACME Corp',
  external_id: 'acme-001',
  email: 'api@acme.com',
  company: 'ACME Corporation',
  description: 'Strategic API partner',
  status: 'active',
  tenant_id: 'tenant-1',
  created_at: '2026-02-01T10:00:00Z',
  updated_at: '2026-02-01T10:00:00Z',
};

describe('ConsumerCard', () => {
  it('should render consumer name', () => {
    render(
      <MemoryRouter>
        <ConsumerCard consumer={mockConsumer} />
      </MemoryRouter>
    );

    expect(screen.getByText('ACME Corp')).toBeInTheDocument();
  });

  it('should render external_id', () => {
    render(
      <MemoryRouter>
        <ConsumerCard consumer={mockConsumer} />
      </MemoryRouter>
    );

    expect(screen.getByText('acme-001')).toBeInTheDocument();
  });

  it('should render status badge as Active', () => {
    render(
      <MemoryRouter>
        <ConsumerCard consumer={mockConsumer} />
      </MemoryRouter>
    );

    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('should render email', () => {
    render(
      <MemoryRouter>
        <ConsumerCard consumer={mockConsumer} />
      </MemoryRouter>
    );

    expect(screen.getByText('api@acme.com')).toBeInTheDocument();
  });

  it('should render company when provided', () => {
    render(
      <MemoryRouter>
        <ConsumerCard consumer={mockConsumer} />
      </MemoryRouter>
    );

    expect(screen.getByText('ACME Corporation')).toBeInTheDocument();
  });

  it('should render description', () => {
    render(
      <MemoryRouter>
        <ConsumerCard consumer={mockConsumer} />
      </MemoryRouter>
    );

    expect(screen.getByText('Strategic API partner')).toBeInTheDocument();
  });

  it('should render suspended status correctly', () => {
    const suspendedConsumer = { ...mockConsumer, status: 'suspended' as const };
    render(
      <MemoryRouter>
        <ConsumerCard consumer={suspendedConsumer} />
      </MemoryRouter>
    );

    expect(screen.getByText('Suspended')).toBeInTheDocument();
  });

  it('should render blocked status correctly', () => {
    const blockedConsumer = { ...mockConsumer, status: 'blocked' as const };
    render(
      <MemoryRouter>
        <ConsumerCard consumer={blockedConsumer} />
      </MemoryRouter>
    );

    expect(screen.getByText('Blocked')).toBeInTheDocument();
  });

  it('should show default description when none provided', () => {
    const noDescConsumer = { ...mockConsumer, description: null };
    render(
      <MemoryRouter>
        <ConsumerCard consumer={noDescConsumer} />
      </MemoryRouter>
    );

    expect(screen.getByText('No description provided')).toBeInTheDocument();
  });

  it('should link to consumer detail page', () => {
    render(
      <MemoryRouter>
        <ConsumerCard consumer={mockConsumer} />
      </MemoryRouter>
    );

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/consumers/c1');
  });

  it('should render formatted date', () => {
    render(
      <MemoryRouter>
        <ConsumerCard consumer={mockConsumer} />
      </MemoryRouter>
    );

    // "Created Feb 1, 2026" or similar format
    expect(screen.getByText(/Created/)).toBeInTheDocument();
  });
});
