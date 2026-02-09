/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Tests for ConsumersPage (CAB-1121)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ConsumersPage } from './ConsumersPage';

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'user-1', name: 'Test User', tenant_id: 'tenant-1', roles: ['tenant-admin'] },
    isAuthenticated: true,
    isReady: true,
  }),
}));

// Mock consumer data
const mockConsumers = [
  {
    id: 'c1',
    name: 'ACME Corp',
    external_id: 'acme-001',
    email: 'api@acme.com',
    company: 'ACME Corporation',
    description: 'Strategic partner',
    status: 'active',
    tenant_id: 'tenant-1',
    created_at: '2026-02-01T10:00:00Z',
    updated_at: '2026-02-01T10:00:00Z',
  },
  {
    id: 'c2',
    name: 'Beta Inc',
    external_id: 'beta-001',
    email: 'dev@beta.com',
    status: 'suspended',
    tenant_id: 'tenant-1',
    created_at: '2026-02-02T10:00:00Z',
    updated_at: '2026-02-02T10:00:00Z',
  },
];

const mockRefetch = vi.fn();
const mockMutateAsync = vi.fn();

// Mock hooks
vi.mock('../../hooks/useConsumers', () => ({
  useConsumers: () => ({
    data: { items: mockConsumers, total: 2, page: 1, pageSize: 20, totalPages: 1 },
    isLoading: false,
    isError: false,
    error: null,
    refetch: mockRefetch,
  }),
  useCreateConsumer: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}));

// Mock ConsumerCard
vi.mock('../../components/consumers/ConsumerCard', () => ({
  ConsumerCard: ({ consumer }: { consumer: any }) => (
    <div data-testid={`consumer-card-${consumer.id}`}>{consumer.name}</div>
  ),
}));

// Mock CreateConsumerModal
vi.mock('../../components/consumers/CreateConsumerModal', () => ({
  CreateConsumerModal: ({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div data-testid="create-modal">Create Modal</div> : null,
}));

describe('ConsumersPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render the page title and description', () => {
    render(
      <MemoryRouter>
        <ConsumersPage />
      </MemoryRouter>
    );

    expect(screen.getByText('Consumers')).toBeInTheDocument();
    expect(screen.getByText('Manage your external API consumers')).toBeInTheDocument();
  });

  it('should render consumer cards', () => {
    render(
      <MemoryRouter>
        <ConsumersPage />
      </MemoryRouter>
    );

    expect(screen.getByTestId('consumer-card-c1')).toHaveTextContent('ACME Corp');
    expect(screen.getByTestId('consumer-card-c2')).toHaveTextContent('Beta Inc');
  });

  it('should render stats cards', () => {
    render(
      <MemoryRouter>
        <ConsumersPage />
      </MemoryRouter>
    );

    expect(screen.getByText('Total')).toBeInTheDocument();
    // "Active" appears in both stats card and filter dropdown, check for multiple
    expect(screen.getAllByText('Active').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Suspended').length).toBeGreaterThanOrEqual(1);
  });

  it('should render search input', () => {
    render(
      <MemoryRouter>
        <ConsumersPage />
      </MemoryRouter>
    );

    expect(screen.getByPlaceholderText('Search by name, ID, or email...')).toBeInTheDocument();
  });

  it('should filter consumers by search query', () => {
    render(
      <MemoryRouter>
        <ConsumersPage />
      </MemoryRouter>
    );

    const searchInput = screen.getByPlaceholderText('Search by name, ID, or email...');
    fireEvent.change(searchInput, { target: { value: 'ACME' } });

    expect(screen.getByTestId('consumer-card-c1')).toBeInTheDocument();
    expect(screen.queryByTestId('consumer-card-c2')).not.toBeInTheDocument();
  });

  it('should open create modal when Register Consumer button is clicked', () => {
    render(
      <MemoryRouter>
        <ConsumersPage />
      </MemoryRouter>
    );

    const button = screen.getByText('Register Consumer');
    fireEvent.click(button);

    expect(screen.getByTestId('create-modal')).toBeInTheDocument();
  });

  it('should display consumer count', () => {
    render(
      <MemoryRouter>
        <ConsumersPage />
      </MemoryRouter>
    );

    expect(screen.getByText('2 consumers')).toBeInTheDocument();
  });
});
