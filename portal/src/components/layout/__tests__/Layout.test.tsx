import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { Layout } from '../Layout';
import { renderWithProviders, createAuthMock } from '../../../test/helpers';

const mockUseAuth = vi.fn();
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('../../../config', () => ({
  config: {
    features: {
      enableI18n: false,
      enableAPICatalog: true,
      enableMCPTools: true,
      enableSubscriptions: true,
      enableGateways: false,
    },
    services: {
      console: { url: 'https://console.gostoa.dev' },
      docs: { url: 'https://docs.gostoa.dev' },
    },
    app: {
      version: '1.0.0',
    },
    baseDomain: 'gostoa.dev',
  },
}));

vi.mock('@stoa/shared/components/StoaLogo', () => ({
  StoaLogo: () => <div data-testid="stoa-logo" />,
}));

vi.mock('@stoa/shared/components/ThemeToggle', () => ({
  ThemeToggle: () => <button data-testid="theme-toggle" />,
}));

vi.mock('../LanguageToggle', () => ({
  LanguageToggle: () => <button data-testid="language-toggle" />,
}));

vi.mock('../../uac', () => ({
  UACSpotlight: ({ onDismiss }: { onDismiss: () => void }) => (
    <div data-testid="uac-spotlight">
      <button onClick={onDismiss}>Dismiss</button>
    </div>
  ),
  useUACSpotlight: () => ({ showSpotlight: false, dismissSpotlight: vi.fn() }),
}));

describe('Layout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));
  });

  it('renders children content', () => {
    renderWithProviders(
      <Layout>
        <div>Test content</div>
      </Layout>
    );

    expect(screen.getByText('Test content')).toBeInTheDocument();
  });

  it('renders the main content area', () => {
    renderWithProviders(
      <Layout>
        <div>hello</div>
      </Layout>
    );

    expect(screen.getByRole('main')).toBeInTheDocument();
  });

  it('renders footer', () => {
    renderWithProviders(
      <Layout>
        <div>content</div>
      </Layout>
    );

    expect(screen.getByText(/STOA Platform/)).toBeInTheDocument();
  });

  it('renders header with logo', () => {
    renderWithProviders(
      <Layout>
        <div>content</div>
      </Layout>
    );

    expect(screen.getByTestId('stoa-logo')).toBeInTheDocument();
  });

  it('does not show UAC spotlight by default', () => {
    renderWithProviders(
      <Layout>
        <div>content</div>
      </Layout>
    );

    expect(screen.queryByTestId('uac-spotlight')).not.toBeInTheDocument();
  });
});
