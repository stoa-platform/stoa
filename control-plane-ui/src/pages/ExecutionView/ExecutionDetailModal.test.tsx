import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ExecutionDetailModal } from './ExecutionDetailModal';

const baseExecution = {
  id: 'exec-1',
  tenant_id: 'test-tenant',
  consumer_id: 'consumer-1',
  api_id: 'api-1',
  api_name: 'Payment API',
  tool_name: 'create-payment',
  request_id: 'req-abc-123',
  method: 'POST',
  path: '/v1/payments',
  status_code: 200,
  status: 'success',
  error_category: null,
  error_message: null,
  started_at: '2026-02-15T10:00:00Z',
  completed_at: '2026-02-15T10:00:01Z',
  duration_ms: 120,
  request_headers: null,
  response_summary: null,
};

describe('ExecutionDetailModal', () => {
  it('renders the modal title', () => {
    render(<ExecutionDetailModal execution={baseExecution} onClose={vi.fn()} />);
    expect(screen.getByText('Execution Detail')).toBeInTheDocument();
  });

  it('displays execution fields', () => {
    render(<ExecutionDetailModal execution={baseExecution} onClose={vi.fn()} />);

    expect(screen.getByText('req-abc-123')).toBeInTheDocument();
    expect(screen.getByText('POST')).toBeInTheDocument();
    expect(screen.getByText('/v1/payments')).toBeInTheDocument();
    expect(screen.getByText('Payment API')).toBeInTheDocument();
    expect(screen.getByText('create-payment')).toBeInTheDocument();
    expect(screen.getByText('120ms')).toBeInTheDocument();
  });

  it('shows status code and status', () => {
    render(<ExecutionDetailModal execution={baseExecution} onClose={vi.fn()} />);
    expect(screen.getByText('200 (success)')).toBeInTheDocument();
  });

  it('calls onClose when close button clicked', () => {
    const onClose = vi.fn();
    render(<ExecutionDetailModal execution={baseExecution} onClose={onClose} />);

    const closeButton = screen.getByLabelText('Close');
    fireEvent.click(closeButton);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when backdrop clicked', () => {
    const onClose = vi.fn();
    render(<ExecutionDetailModal execution={baseExecution} onClose={onClose} />);

    const backdrop = screen.getByRole('dialog');
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('shows error message when present', () => {
    const exec = { ...baseExecution, error_message: 'Connection timeout', status: 'error' };
    render(<ExecutionDetailModal execution={exec} onClose={vi.fn()} />);

    expect(screen.getByText('Error Message')).toBeInTheDocument();
    expect(screen.getByText('Connection timeout')).toBeInTheDocument();
  });

  it('shows request headers when present', () => {
    const exec = {
      ...baseExecution,
      request_headers: { 'Content-Type': 'application/json' },
    };
    render(<ExecutionDetailModal execution={exec} onClose={vi.fn()} />);

    expect(screen.getByText('Request Headers')).toBeInTheDocument();
  });

  it('shows response summary when present', () => {
    const exec = { ...baseExecution, response_summary: { status: 'ok' } };
    render(<ExecutionDetailModal execution={exec} onClose={vi.fn()} />);

    expect(screen.getByText('Response Summary')).toBeInTheDocument();
  });

  it('shows dashes for null fields', () => {
    const exec = {
      ...baseExecution,
      method: null,
      path: null,
      api_name: null,
      tool_name: null,
      duration_ms: null,
    };
    render(<ExecutionDetailModal execution={exec} onClose={vi.fn()} />);

    // Multiple "—" for null fields
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThanOrEqual(4);
  });
});
