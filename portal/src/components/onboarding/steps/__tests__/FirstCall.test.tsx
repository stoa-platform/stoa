/**
 * FirstCall Step Tests (CAB-1325)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithProviders, createAuthMock } from '../../../../test/helpers';
import { FirstCall } from '../FirstCall';

// Mock hooks
const mockTrialKey = {
  key_prefix: 'stoa_trial_abc',
  name: 'trial-key',
  rate_limit_rpm: 100,
  expires_at: '2026-03-20T00:00:00Z',
  status: 'active',
  created_at: '2026-02-19T00:00:00Z',
};

vi.mock('../../../../hooks/useOnboarding', () => ({
  useTrialKey: () => ({ data: mockTrialKey }),
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

const mockOnFinish = vi.fn();

describe('FirstCall — normal mode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders credentials in normal mode with app', () => {
    renderWithProviders(
      <FirstCall
        app={{
          id: 'app-1',
          name: 'my-app',
          clientId: 'client-123',
          clientSecret: 'secret-xyz',
          callbackUrls: [],
          userId: 'u1',
          status: 'active',
          createdAt: '2026-01-01T00:00:00Z',
          updatedAt: '2026-01-01T00:00:00Z',
        }}
        selectedApi={null}
        useCase="rest-api"
        onFinish={mockOnFinish}
      />
    );

    expect(screen.getByText('firstCall.title')).toBeInTheDocument();
    expect(screen.getByText('firstCall.credentials')).toBeInTheDocument();
    expect(screen.getByText('client-123')).toBeInTheDocument();
    expect(screen.getByText('secret-xyz')).toBeInTheDocument();
  });

  it('shows MCP config for mcp-agent use case', () => {
    renderWithProviders(
      <FirstCall
        app={{
          id: 'app-1',
          name: 'my-app',
          clientId: 'client-123',
          callbackUrls: [],
          userId: 'u1',
          status: 'active',
          createdAt: '2026-01-01T00:00:00Z',
          updatedAt: '2026-01-01T00:00:00Z',
        }}
        selectedApi={null}
        useCase="mcp-agent"
        onFinish={mockOnFinish}
      />
    );

    expect(screen.getByText('firstCall.mcpConfig')).toBeInTheDocument();
  });

  it('calls onFinish when dashboard button clicked', () => {
    renderWithProviders(
      <FirstCall app={null} selectedApi={null} useCase="rest-api" onFinish={mockOnFinish} />
    );

    fireEvent.click(screen.getByText('firstCall.goToDashboard'));
    expect(mockOnFinish).toHaveBeenCalledTimes(1);
  });
});

describe('FirstCall — sandbox mode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders sandbox title and trial key info', () => {
    renderWithProviders(
      <FirstCall
        app={null}
        selectedApi={null}
        useCase="rest-api"
        sandboxMode
        onFinish={mockOnFinish}
      />
    );

    expect(screen.getByText('Try the Sandbox')).toBeInTheDocument();
    expect(screen.getByText('Your Trial API Key')).toBeInTheDocument();
    expect(screen.getByText('stoa_trial_abc...')).toBeInTheDocument();
    expect(screen.getByText('100 req/min')).toBeInTheDocument();
  });

  it('shows sandbox curl command with sandbox echo tool', () => {
    const { container } = renderWithProviders(
      <FirstCall
        app={null}
        selectedApi={null}
        useCase="rest-api"
        sandboxMode
        onFinish={mockOnFinish}
      />
    );
    const codeElements = container.querySelectorAll('code');
    const hasSandboxEcho = Array.from(codeElements).some((el) =>
      el.textContent?.includes('stoa_sandbox_echo')
    );
    expect(hasSandboxEcho).toBe(true);
  });

  it('shows MCP config in sandbox mode', () => {
    const { container } = renderWithProviders(
      <FirstCall
        app={null}
        selectedApi={null}
        useCase="rest-api"
        sandboxMode
        onFinish={mockOnFinish}
      />
    );

    expect(screen.getByText('MCP Configuration')).toBeInTheDocument();
    const codeElements = container.querySelectorAll('code');
    const hasSandboxConfig = Array.from(codeElements).some((el) =>
      el.textContent?.includes('stoa-sandbox')
    );
    expect(hasSandboxConfig).toBe(true);
  });
});
