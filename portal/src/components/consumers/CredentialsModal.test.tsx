import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CredentialsModal } from './CredentialsModal';
import type { ConsumerCredentials } from '../../types';

vi.mock('./TokenExchangePanel', () => ({
  TokenExchangePanel: ({ consumerName }: { consumerName: string }) => (
    <div data-testid="token-exchange">TokenExchange: {consumerName}</div>
  ),
}));

const mockCredentials: ConsumerCredentials = {
  consumer_id: 'consumer-1',
  client_id: 'stoa-client-abc123',
  client_secret: 'super-secret-xyz789',
  token_endpoint: 'https://auth.example.com/oauth/token',
  grant_type: 'client_credentials',
};

const defaultProps = {
  isOpen: true,
  onClose: vi.fn(),
  credentials: mockCredentials,
  consumerName: 'My Weather Consumer',
};

describe('CredentialsModal', () => {
  it('should return null when not open', () => {
    const { container } = render(<CredentialsModal {...defaultProps} isOpen={false} />);
    expect(container.firstChild).toBeNull();
  });

  it('should render title and consumer name', () => {
    render(<CredentialsModal {...defaultProps} />);
    expect(screen.getByText('Consumer Credentials')).toBeInTheDocument();
    expect(screen.getByText('My Weather Consumer')).toBeInTheDocument();
  });

  it('should show security warning', () => {
    render(<CredentialsModal {...defaultProps} />);
    expect(screen.getByText(/Save these credentials now/)).toBeInTheDocument();
  });

  it('should display client ID', () => {
    render(<CredentialsModal {...defaultProps} />);
    expect(screen.getByText('Client ID')).toBeInTheDocument();
    expect(screen.getByText('stoa-client-abc123')).toBeInTheDocument();
  });

  it('should display client secret', () => {
    render(<CredentialsModal {...defaultProps} />);
    expect(screen.getByText('Client Secret')).toBeInTheDocument();
    expect(screen.getByText('super-secret-xyz789')).toBeInTheDocument();
  });

  it('should display token endpoint', () => {
    render(<CredentialsModal {...defaultProps} />);
    expect(screen.getByText('Token Endpoint')).toBeInTheDocument();
    expect(screen.getByText('https://auth.example.com/oauth/token')).toBeInTheDocument();
  });

  it('should display grant type', () => {
    render(<CredentialsModal {...defaultProps} />);
    expect(screen.getByText('Grant Type')).toBeInTheDocument();
    expect(screen.getByText('client_credentials')).toBeInTheDocument();
  });

  it('should show cURL snippet', () => {
    render(<CredentialsModal {...defaultProps} />);
    expect(screen.getByText('Quick Test')).toBeInTheDocument();
    expect(screen.getByText(/grant_type=client_credentials/)).toBeInTheDocument();
  });

  it('should copy client ID to clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    render(<CredentialsModal {...defaultProps} />);
    fireEvent.click(screen.getByTitle('Copy Client ID'));
    expect(writeText).toHaveBeenCalledWith('stoa-client-abc123');
  });

  it('should call onClose on Done click', () => {
    render(<CredentialsModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Done'));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('should not show TokenExchangePanel without tenantId and consumerId', () => {
    render(<CredentialsModal {...defaultProps} />);
    expect(screen.queryByTestId('token-exchange')).not.toBeInTheDocument();
  });

  it('should show TokenExchangePanel when tenantId and consumerId provided', () => {
    render(<CredentialsModal {...defaultProps} tenantId="tenant-1" consumerId="consumer-1" />);
    expect(screen.getByTestId('token-exchange')).toBeInTheDocument();
  });
});
