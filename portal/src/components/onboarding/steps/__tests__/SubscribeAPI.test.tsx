/**
 * SubscribeAPI Step Tests (CAB-1325)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithProviders, createAuthMock } from '../../../../test/helpers';
import { SubscribeAPI } from '../SubscribeAPI';

const mockAPIsData = {
  items: [
    {
      id: 'api-1',
      name: 'Pet Store API',
      version: '1.0',
      description: 'Manage pet store inventory',
      tenantId: 't1',
      status: 'published' as const,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    },
  ],
  total: 1,
  page: 1,
  pageSize: 6,
  totalPages: 1,
};

vi.mock('../../../../hooks/useAPIs', () => ({
  useAPIs: () => ({
    data: mockAPIsData,
    isLoading: false,
  }),
}));

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => createAuthMock('cpi-admin'),
}));

vi.mock('../../../../i18n', () => ({}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, fallback?: string) => fallback ?? k,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}));

const mockOnSelected = vi.fn();
const mockOnBack = vi.fn();
const mockOnSkip = vi.fn();
const mockOnSandbox = vi.fn();

describe('SubscribeAPI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders sandbox shortcut when onSandbox provided', () => {
    renderWithProviders(
      <SubscribeAPI
        onSelected={mockOnSelected}
        onBack={mockOnBack}
        onSkip={mockOnSkip}
        onSandbox={mockOnSandbox}
      />
    );

    expect(screen.getByText('Try demo tools instantly')).toBeInTheDocument();
    expect(screen.getByText('Try Sandbox')).toBeInTheDocument();
  });

  it('does not render sandbox shortcut without onSandbox', () => {
    renderWithProviders(
      <SubscribeAPI onSelected={mockOnSelected} onBack={mockOnBack} onSkip={mockOnSkip} />
    );

    expect(screen.queryByText('Try demo tools instantly')).not.toBeInTheDocument();
  });

  it('calls onSandbox when sandbox button clicked', () => {
    renderWithProviders(
      <SubscribeAPI
        onSelected={mockOnSelected}
        onBack={mockOnBack}
        onSkip={mockOnSkip}
        onSandbox={mockOnSandbox}
      />
    );

    fireEvent.click(screen.getByText('Try Sandbox'));
    expect(mockOnSandbox).toHaveBeenCalledTimes(1);
  });

  it('renders API cards from the catalog', () => {
    renderWithProviders(
      <SubscribeAPI
        onSelected={mockOnSelected}
        onBack={mockOnBack}
        onSkip={mockOnSkip}
        onSandbox={mockOnSandbox}
      />
    );

    expect(screen.getByText('Pet Store API')).toBeInTheDocument();
  });
});
