import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TokenExchangePanel } from './TokenExchangePanel';

vi.mock('../../services/consumers', () => ({
  consumersService: {
    exchangeToken: vi.fn(),
  },
}));

import { consumersService } from '../../services/consumers';

describe('TokenExchangePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render the panel with header', () => {
    render(<TokenExchangePanel tenantId="t1" consumerId="c1" consumerName="Test Consumer" />);
    expect(screen.getByText('Token Exchange (RFC 8693)')).toBeInTheDocument();
  });

  it('should render subject token input', () => {
    render(<TokenExchangePanel tenantId="t1" consumerId="c1" consumerName="Test Consumer" />);
    expect(screen.getByLabelText('Subject Token')).toBeInTheDocument();
  });

  it('should render optional audience and scope fields', () => {
    render(<TokenExchangePanel tenantId="t1" consumerId="c1" consumerName="Test Consumer" />);
    expect(screen.getByLabelText(/Audience/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Scope/)).toBeInTheDocument();
  });

  it('should disable exchange button when no subject token', () => {
    render(<TokenExchangePanel tenantId="t1" consumerId="c1" consumerName="Test Consumer" />);
    expect(screen.getByText('Exchange Token')).toBeDisabled();
  });

  it('should enable exchange button when subject token entered', () => {
    render(<TokenExchangePanel tenantId="t1" consumerId="c1" consumerName="Test Consumer" />);
    fireEvent.change(screen.getByLabelText('Subject Token'), {
      target: { value: 'eyJhbGciOiJSUzI1NiJ9.payload.sig' },
    });
    expect(screen.getByText('Exchange Token')).not.toBeDisabled();
  });

  it('should call exchangeToken service on submit', async () => {
    vi.mocked(consumersService.exchangeToken).mockResolvedValue({
      access_token: 'eyJ.new.token',
      token_type: 'Bearer',
      expires_in: 300,
    });

    render(<TokenExchangePanel tenantId="t1" consumerId="c1" consumerName="Test Consumer" />);
    fireEvent.change(screen.getByLabelText('Subject Token'), {
      target: { value: 'old-token' },
    });
    fireEvent.click(screen.getByText('Exchange Token'));

    await waitFor(() => {
      expect(consumersService.exchangeToken).toHaveBeenCalledWith('t1', 'c1', {
        subject_token: 'old-token',
        audience: undefined,
        scope: undefined,
      });
    });
  });

  it('should display exchanged token on success', async () => {
    vi.mocked(consumersService.exchangeToken).mockResolvedValue({
      access_token: 'new-access-token-abc',
      token_type: 'Bearer',
      expires_in: 300,
    });

    render(<TokenExchangePanel tenantId="t1" consumerId="c1" consumerName="Test Consumer" />);
    fireEvent.change(screen.getByLabelText('Subject Token'), {
      target: { value: 'old-token' },
    });
    fireEvent.click(screen.getByText('Exchange Token'));

    await waitFor(() => {
      expect(screen.getByText('Exchanged Token')).toBeInTheDocument();
      expect(screen.getByText('new-access-token-abc')).toBeInTheDocument();
    });
  });

  it('should show expires_in on success', async () => {
    vi.mocked(consumersService.exchangeToken).mockResolvedValue({
      access_token: 'token',
      token_type: 'Bearer',
      expires_in: 300,
    });

    render(<TokenExchangePanel tenantId="t1" consumerId="c1" consumerName="Test Consumer" />);
    fireEvent.change(screen.getByLabelText('Subject Token'), {
      target: { value: 'old-token' },
    });
    fireEvent.click(screen.getByText('Exchange Token'));

    await waitFor(() => {
      expect(screen.getByText('expires in 300s')).toBeInTheDocument();
    });
  });

  it('should show error on failure', async () => {
    vi.mocked(consumersService.exchangeToken).mockRejectedValue({
      response: { data: { detail: 'Invalid subject token' } },
    });

    render(<TokenExchangePanel tenantId="t1" consumerId="c1" consumerName="Test Consumer" />);
    fireEvent.change(screen.getByLabelText('Subject Token'), {
      target: { value: 'bad-token' },
    });
    fireEvent.click(screen.getByText('Exchange Token'));

    await waitFor(() => {
      expect(screen.getByText('Invalid subject token')).toBeInTheDocument();
    });
  });

  it('should show cURL snippet after exchange', async () => {
    vi.mocked(consumersService.exchangeToken).mockResolvedValue({
      access_token: 'my-token',
      token_type: 'Bearer',
      expires_in: 300,
    });

    render(<TokenExchangePanel tenantId="t1" consumerId="c1" consumerName="Test Consumer" />);
    fireEvent.change(screen.getByLabelText('Subject Token'), {
      target: { value: 'old-token' },
    });
    fireEvent.click(screen.getByText('Exchange Token'));

    await waitFor(() => {
      expect(screen.getByText('Quick Test')).toBeInTheDocument();
    });
  });

  it('should pass audience and scope when provided', async () => {
    vi.mocked(consumersService.exchangeToken).mockResolvedValue({
      access_token: 'token',
      token_type: 'Bearer',
      expires_in: 60,
    });

    render(<TokenExchangePanel tenantId="t1" consumerId="c1" consumerName="Test Consumer" />);
    fireEvent.change(screen.getByLabelText('Subject Token'), {
      target: { value: 'tok' },
    });
    fireEvent.change(screen.getByLabelText(/Audience/), {
      target: { value: 'stoa-api' },
    });
    fireEvent.change(screen.getByLabelText(/Scope/), {
      target: { value: 'openid' },
    });
    fireEvent.click(screen.getByText('Exchange Token'));

    await waitFor(() => {
      expect(consumersService.exchangeToken).toHaveBeenCalledWith('t1', 'c1', {
        subject_token: 'tok',
        audience: 'stoa-api',
        scope: 'openid',
      });
    });
  });
});
