import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { CredentialsViewer } from './CredentialsViewer';
import { renderWithProviders } from '../../test/helpers';

describe('CredentialsViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it('should always render the Client ID value', () => {
    renderWithProviders(<CredentialsViewer clientId="client-abc123" />);
    expect(screen.getByText('client-abc123')).toBeInTheDocument();
  });

  it('should mask the secret by default when clientSecret is provided', () => {
    renderWithProviders(
      <CredentialsViewer clientId="client-abc123" clientSecret="super-secret-value" />
    );
    expect(screen.getByText('••••••••••••••••••••••••••••••••')).toBeInTheDocument();
    expect(screen.queryByText('super-secret-value')).not.toBeInTheDocument();
  });

  it('should toggle secret visibility with the eye button', () => {
    renderWithProviders(
      <CredentialsViewer clientId="client-abc123" clientSecret="super-secret-value" />
    );
    // Initially masked
    expect(screen.getByText('••••••••••••••••••••••••••••••••')).toBeInTheDocument();

    // Click the show button (title="Show secret")
    const showBtn = screen.getByTitle('Show secret');
    fireEvent.click(showBtn);

    expect(screen.getByText('super-secret-value')).toBeInTheDocument();
    expect(screen.queryByText('••••••••••••••••••••••••••••••••')).not.toBeInTheDocument();

    // Click again to hide
    const hideBtn = screen.getByTitle('Hide secret');
    fireEvent.click(hideBtn);
    expect(screen.getByText('••••••••••••••••••••••••••••••••')).toBeInTheDocument();
  });

  it('should call clipboard.writeText with clientId when copy button is clicked', async () => {
    renderWithProviders(<CredentialsViewer clientId="client-abc123" />);
    const copyBtn = screen.getByTitle('Copy Client ID');
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('client-abc123');
    });
  });

  it('should show warning banner and reveal secret when showSecretOnce is true', () => {
    renderWithProviders(
      <CredentialsViewer
        clientId="client-abc123"
        clientSecret="once-revealed-secret"
        showSecretOnce={true}
      />
    );
    // Secret should be revealed (not masked)
    expect(screen.getByText('once-revealed-secret')).toBeInTheDocument();
    // Warning banner should be shown
    expect(screen.getByText(/this secret will only be shown once/i)).toBeInTheDocument();
  });

  it('should show "Secret is hidden" fallback when no clientSecret is provided', () => {
    renderWithProviders(<CredentialsViewer clientId="client-abc123" />);
    expect(screen.getByText(/secret is hidden\. regenerate to get a new one/i)).toBeInTheDocument();
  });

  it('should show "Regenerate Secret" button when onRegenerateSecret is provided', () => {
    const onRegenerate = vi.fn().mockResolvedValue('new-secret-value');
    renderWithProviders(
      <CredentialsViewer
        clientId="client-abc123"
        clientSecret="current-secret"
        onRegenerateSecret={onRegenerate}
      />
    );
    expect(screen.getByText('Regenerate Secret')).toBeInTheDocument();
  });

  it('should show confirmation warning panel when "Regenerate Secret" is clicked', () => {
    const onRegenerate = vi.fn().mockResolvedValue('new-secret-value');
    renderWithProviders(
      <CredentialsViewer
        clientId="client-abc123"
        clientSecret="current-secret"
        onRegenerateSecret={onRegenerate}
      />
    );
    fireEvent.click(screen.getByText('Regenerate Secret'));
    expect(screen.getByText(/are you sure you want to regenerate the secret/i)).toBeInTheDocument();
    expect(screen.getByText('Yes, Regenerate')).toBeInTheDocument();
  });

  it('should call onRegenerateSecret when confirming regeneration', async () => {
    const onRegenerate = vi.fn().mockResolvedValue('new-secret-value');
    renderWithProviders(
      <CredentialsViewer
        clientId="client-abc123"
        clientSecret="current-secret"
        onRegenerateSecret={onRegenerate}
      />
    );
    fireEvent.click(screen.getByText('Regenerate Secret'));
    fireEvent.click(screen.getByText('Yes, Regenerate'));

    await waitFor(() => {
      expect(onRegenerate).toHaveBeenCalled();
    });
  });

  it('should dismiss the confirmation panel when Cancel is clicked', () => {
    const onRegenerate = vi.fn().mockResolvedValue('new-secret-value');
    renderWithProviders(
      <CredentialsViewer
        clientId="client-abc123"
        clientSecret="current-secret"
        onRegenerateSecret={onRegenerate}
      />
    );
    fireEvent.click(screen.getByText('Regenerate Secret'));
    expect(screen.getByText('Yes, Regenerate')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByText('Yes, Regenerate')).not.toBeInTheDocument();
    expect(screen.getByText('Regenerate Secret')).toBeInTheDocument();
  });
});
