/**
 * Tests for CredentialsDisplay component (CAB-1121)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CredentialsDisplay } from './CredentialsDisplay';
import type { ConsumerCredentials } from '../../types';

const mockCredentials: ConsumerCredentials = {
  consumer_id: 'c1',
  client_id: 'stoa-client-acme-001',
  client_secret: 'super-secret-value-12345',
  token_endpoint: 'https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token',
  grant_type: 'client_credentials',
};

describe('CredentialsDisplay', () => {
  beforeEach(() => {
    // Mock clipboard API
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it('should render client_id', () => {
    render(<CredentialsDisplay credentials={mockCredentials} />);

    expect(screen.getByText('stoa-client-acme-001')).toBeInTheDocument();
  });

  it('should render client_secret visible by default', () => {
    render(<CredentialsDisplay credentials={mockCredentials} />);

    expect(screen.getByText('super-secret-value-12345')).toBeInTheDocument();
  });

  it('should render token endpoint', () => {
    render(<CredentialsDisplay credentials={mockCredentials} />);

    expect(
      screen.getByText('https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token')
    ).toBeInTheDocument();
  });

  it('should render grant type', () => {
    render(<CredentialsDisplay credentials={mockCredentials} />);

    expect(screen.getByText('client_credentials')).toBeInTheDocument();
  });

  it('should show one-time warning', () => {
    render(<CredentialsDisplay credentials={mockCredentials} />);

    expect(screen.getByText(/The client secret is only shown once/)).toBeInTheDocument();
  });

  it('should toggle secret visibility', () => {
    render(<CredentialsDisplay credentials={mockCredentials} />);

    // Initially visible
    expect(screen.getByText('super-secret-value-12345')).toBeInTheDocument();

    // Click hide button
    const hideButton = screen.getByTitle('Hide secret');
    fireEvent.click(hideButton);

    // Should be masked now
    expect(screen.queryByText('super-secret-value-12345')).not.toBeInTheDocument();

    // Click show button
    const showButton = screen.getByTitle('Show secret');
    fireEvent.click(showButton);

    // Should be visible again
    expect(screen.getByText('super-secret-value-12345')).toBeInTheDocument();
  });

  it('should copy client_id to clipboard', async () => {
    render(<CredentialsDisplay credentials={mockCredentials} />);

    const copyButton = screen.getByTitle('Copy Client ID');
    fireEvent.click(copyButton);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('stoa-client-acme-001');
  });

  it('should copy client_secret to clipboard', async () => {
    render(<CredentialsDisplay credentials={mockCredentials} />);

    const copyButton = screen.getByTitle('Copy Client Secret');
    fireEvent.click(copyButton);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('super-secret-value-12345');
  });

  it('should copy token endpoint to clipboard', async () => {
    render(<CredentialsDisplay credentials={mockCredentials} />);

    const copyButton = screen.getByTitle('Copy Token Endpoint');
    fireEvent.click(copyButton);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      'https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token'
    );
  });

  it('should render all field labels', () => {
    render(<CredentialsDisplay credentials={mockCredentials} />);

    expect(screen.getByText('Client ID')).toBeInTheDocument();
    expect(screen.getByText('Client Secret')).toBeInTheDocument();
    expect(screen.getByText('Token Endpoint')).toBeInTheDocument();
  });
});
