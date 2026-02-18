import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { FirstCall } from '../FirstCall';
import { renderWithProviders, mockApplication, mockAPI } from '../../../../test/helpers';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('../../../../config', () => ({
  config: {
    api: { baseUrl: 'https://api.example.com' },
    mcp: { baseUrl: 'https://mcp.example.com' },
    services: {
      docs: { url: 'https://docs.example.com' },
    },
  },
}));

// Mock clipboard API
Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn().mockResolvedValue(undefined),
  },
});

describe('FirstCall', () => {
  const app = mockApplication({
    name: 'my-app',
    clientId: 'client-123',
    clientSecret: 'secret-abc',
  });
  const api = mockAPI({ id: 'api-1', name: 'Payment API' });
  const onFinish = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    onFinish.mockReset();
    vi.mocked(navigator.clipboard.writeText).mockResolvedValue(undefined);
  });

  it('renders title via i18n', () => {
    renderWithProviders(
      <FirstCall
        app={app as never}
        selectedApi={api as never}
        useCase="rest-api"
        onFinish={onFinish}
      />
    );

    expect(screen.getByText('firstCall.title')).toBeInTheDocument();
  });

  it('renders subtitle via i18n', () => {
    renderWithProviders(
      <FirstCall
        app={app as never}
        selectedApi={api as never}
        useCase="rest-api"
        onFinish={onFinish}
      />
    );

    expect(screen.getByText('firstCall.subtitle')).toBeInTheDocument();
  });

  it('renders credentials section when app provided', () => {
    renderWithProviders(
      <FirstCall app={app as never} selectedApi={null} useCase="rest-api" onFinish={onFinish} />
    );

    expect(screen.getByText('firstCall.credentials')).toBeInTheDocument();
    expect(screen.getByText('my-app')).toBeInTheDocument();
    expect(screen.getByText('client-123')).toBeInTheDocument();
  });

  it('shows client secret in credentials', () => {
    renderWithProviders(
      <FirstCall app={app as never} selectedApi={null} useCase="rest-api" onFinish={onFinish} />
    );

    expect(screen.getByText('secret-abc')).toBeInTheDocument();
  });

  it('shows secret warning when clientSecret is present', () => {
    renderWithProviders(
      <FirstCall app={app as never} selectedApi={null} useCase="rest-api" onFinish={onFinish} />
    );

    expect(screen.getByText('firstCall.secretWarning')).toBeInTheDocument();
  });

  it('does not render credentials when no app', () => {
    renderWithProviders(
      <FirstCall app={null} selectedApi={null} useCase="rest-api" onFinish={onFinish} />
    );

    expect(screen.queryByText('firstCall.credentials')).not.toBeInTheDocument();
  });

  it('renders curl example for rest-api use case', () => {
    renderWithProviders(
      <FirstCall app={null} selectedApi={api as never} useCase="rest-api" onFinish={onFinish} />
    );

    expect(screen.getByText('firstCall.exampleCall')).toBeInTheDocument();
    expect(screen.getByText(/curl -X GET/)).toBeInTheDocument();
  });

  it('renders MCP config for mcp-agent use case', () => {
    renderWithProviders(
      <FirstCall app={app as never} selectedApi={null} useCase="mcp-agent" onFinish={onFinish} />
    );

    expect(screen.getByText('firstCall.mcpConfig')).toBeInTheDocument();
    expect(screen.getByText(/mcpServers/)).toBeInTheDocument();
  });

  it('renders finish button', () => {
    renderWithProviders(
      <FirstCall app={null} selectedApi={null} useCase="rest-api" onFinish={onFinish} />
    );

    expect(screen.getByText('firstCall.goToDashboard')).toBeInTheDocument();
  });

  it('calls onFinish when finish button clicked', () => {
    renderWithProviders(
      <FirstCall app={null} selectedApi={null} useCase="rest-api" onFinish={onFinish} />
    );

    fireEvent.click(screen.getByText('firstCall.goToDashboard'));
    expect(onFinish).toHaveBeenCalledOnce();
  });

  it('renders documentation link', () => {
    renderWithProviders(
      <FirstCall app={null} selectedApi={null} useCase="rest-api" onFinish={onFinish} />
    );

    expect(screen.getByText('firstCall.documentation')).toBeInTheDocument();
  });

  it('renders sandbox link when selectedApi is provided', () => {
    renderWithProviders(
      <FirstCall app={null} selectedApi={api as never} useCase="rest-api" onFinish={onFinish} />
    );

    expect(screen.getByText('firstCall.trySandbox')).toBeInTheDocument();
  });

  it('copies code to clipboard when copy button clicked', async () => {
    renderWithProviders(
      <FirstCall app={null} selectedApi={null} useCase="rest-api" onFinish={onFinish} />
    );

    fireEvent.click(screen.getByText('firstCall.copy'));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalled();
    });
  });
});
