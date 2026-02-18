import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { CredentialsViewer } from '../CredentialsViewer';
import { renderWithProviders } from '../../../test/helpers';

// Mock clipboard API
Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn().mockResolvedValue(undefined),
  },
});

describe('CredentialsViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(navigator.clipboard.writeText).mockResolvedValue(undefined);
  });

  it('renders client ID', () => {
    renderWithProviders(<CredentialsViewer clientId="client-abc123" />);

    expect(screen.getByText('client-abc123')).toBeInTheDocument();
    expect(screen.getByText('Client ID')).toBeInTheDocument();
  });

  it('renders hidden state when no clientSecret', () => {
    renderWithProviders(<CredentialsViewer clientId="client-abc123" />);

    expect(screen.getByText('Secret is hidden. Regenerate to get a new one.')).toBeInTheDocument();
  });

  it('renders masked secret when clientSecret provided', () => {
    renderWithProviders(
      <CredentialsViewer clientId="client-abc123" clientSecret="super-secret-value" />
    );

    expect(screen.getByText('Client Secret')).toBeInTheDocument();
    // Secret masked by default
    expect(screen.getByText('••••••••••••••••••••••••••••••••')).toBeInTheDocument();
  });

  it('reveals secret when showSecretOnce is true', () => {
    renderWithProviders(
      <CredentialsViewer clientId="client-abc123" clientSecret="my-secret" showSecretOnce={true} />
    );

    expect(screen.getByText('my-secret')).toBeInTheDocument();
  });

  it('shows warning when showSecretOnce is true', () => {
    renderWithProviders(
      <CredentialsViewer clientId="client-abc123" clientSecret="my-secret" showSecretOnce={true} />
    );

    expect(screen.getByText(/only be shown once/)).toBeInTheDocument();
  });

  it('toggles secret visibility when eye button clicked', () => {
    renderWithProviders(<CredentialsViewer clientId="client-abc123" clientSecret="my-secret" />);

    // Initially masked
    expect(screen.getByText('••••••••••••••••••••••••••••••••')).toBeInTheDocument();

    // Click to show
    fireEvent.click(screen.getByTitle('Show secret'));
    expect(screen.getByText('my-secret')).toBeInTheDocument();

    // Click to hide again
    fireEvent.click(screen.getByTitle('Hide secret'));
    expect(screen.getByText('••••••••••••••••••••••••••••••••')).toBeInTheDocument();
  });

  it('copies client ID to clipboard', async () => {
    renderWithProviders(<CredentialsViewer clientId="client-abc123" />);

    fireEvent.click(screen.getByTitle('Copy Client ID'));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('client-abc123');
    });
  });

  it('copies client secret to clipboard', async () => {
    renderWithProviders(<CredentialsViewer clientId="client-abc123" clientSecret="my-secret" />);

    fireEvent.click(screen.getByTitle('Copy Client Secret'));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('my-secret');
    });
  });

  it('renders Regenerate Secret button when onRegenerateSecret provided', () => {
    const onRegenerate = vi.fn().mockResolvedValue('new-secret');
    renderWithProviders(
      <CredentialsViewer clientId="client-abc123" onRegenerateSecret={onRegenerate} />
    );

    expect(screen.getByText('Regenerate Secret')).toBeInTheDocument();
  });

  it('does not render Regenerate Secret button when no callback', () => {
    renderWithProviders(<CredentialsViewer clientId="client-abc123" />);

    expect(screen.queryByText('Regenerate Secret')).not.toBeInTheDocument();
  });

  it('shows confirmation dialog before regenerating', () => {
    const onRegenerate = vi.fn().mockResolvedValue('new-secret');
    renderWithProviders(
      <CredentialsViewer clientId="client-abc123" onRegenerateSecret={onRegenerate} />
    );

    fireEvent.click(screen.getByText('Regenerate Secret'));

    expect(screen.getByText('Are you sure you want to regenerate the secret?')).toBeInTheDocument();
    expect(screen.getByText('Yes, Regenerate')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('calls onRegenerateSecret when confirmed', async () => {
    const onRegenerate = vi.fn().mockResolvedValue('new-secret');
    renderWithProviders(
      <CredentialsViewer clientId="client-abc123" onRegenerateSecret={onRegenerate} />
    );

    fireEvent.click(screen.getByText('Regenerate Secret'));
    fireEvent.click(screen.getByText('Yes, Regenerate'));

    await waitFor(() => {
      expect(onRegenerate).toHaveBeenCalledOnce();
    });
  });

  it('shows regenerating state when isRegenerating is true', () => {
    const onRegenerate = vi.fn();
    renderWithProviders(
      <CredentialsViewer
        clientId="client-abc123"
        onRegenerateSecret={onRegenerate}
        isRegenerating={true}
      />
    );

    expect(screen.getByText('Regenerate Secret')).toBeDisabled();
  });
});
