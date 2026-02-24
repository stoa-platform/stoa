import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ResponseViewer, type ResponseData } from './ResponseViewer';
import { renderWithProviders } from '../../test/helpers';

const mockSuccessResponse: ResponseData = {
  status: 200,
  statusText: 'OK',
  headers: {
    'content-type': 'application/json',
    'x-request-id': 'req-123',
  },
  body: { message: 'Hello World', count: 42 },
  timing: { total: 185, dns: 5, tcp: 15, ttfb: 45 },
};

const mockErrorResponse: ResponseData = {
  status: 500,
  statusText: 'Internal Server Error',
  headers: { 'content-type': 'application/json' },
  body: { error: 'Something went wrong' },
  timing: { total: 2500 },
  error: 'Connection refused',
};

const mock404Response: ResponseData = {
  status: 404,
  statusText: 'Not Found',
  headers: {},
  body: { detail: 'Resource not found' },
  timing: { total: 50 },
};

describe('ResponseViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should show empty state when no response', () => {
    renderWithProviders(<ResponseViewer response={null} />);
    expect(screen.getByText('No Response Yet')).toBeInTheDocument();
    expect(screen.getByText(/Configure your request above/)).toBeInTheDocument();
  });

  it('should show loading state', () => {
    renderWithProviders(<ResponseViewer response={null} isLoading={true} />);
    expect(screen.getByText('Sending request...')).toBeInTheDocument();
  });

  it('should display 200 status with green indicator', () => {
    renderWithProviders(<ResponseViewer response={mockSuccessResponse} />);
    expect(screen.getByText('200')).toBeInTheDocument();
    expect(screen.getByText('OK')).toBeInTheDocument();
  });

  it('should display response timing', () => {
    renderWithProviders(<ResponseViewer response={mockSuccessResponse} />);
    expect(screen.getByText('185ms')).toBeInTheDocument();
  });

  it('should display timing breakdown when available', () => {
    renderWithProviders(<ResponseViewer response={mockSuccessResponse} />);
    expect(screen.getByText(/DNS: 5ms/)).toBeInTheDocument();
    expect(screen.getByText(/TCP: 15ms/)).toBeInTheDocument();
    expect(screen.getByText(/TTFB: 45ms/)).toBeInTheDocument();
  });

  it('should format long timing as seconds', () => {
    renderWithProviders(<ResponseViewer response={mockErrorResponse} />);
    expect(screen.getByText('2.50s')).toBeInTheDocument();
  });

  it('should display JSON body', () => {
    renderWithProviders(<ResponseViewer response={mockSuccessResponse} />);
    expect(screen.getByText(/"message": "Hello World"/)).toBeInTheDocument();
    expect(screen.getByText(/"count": 42/)).toBeInTheDocument();
  });

  it('should show error message for failed requests', () => {
    renderWithProviders(<ResponseViewer response={mockErrorResponse} />);
    expect(screen.getByText('Request Failed')).toBeInTheDocument();
    expect(screen.getByText('Connection refused')).toBeInTheDocument();
  });

  it('should display 500 status', () => {
    renderWithProviders(<ResponseViewer response={mockErrorResponse} />);
    expect(screen.getByText('500')).toBeInTheDocument();
    expect(screen.getByText('Internal Server Error')).toBeInTheDocument();
  });

  it('should display 404 status', () => {
    renderWithProviders(<ResponseViewer response={mock404Response} />);
    expect(screen.getByText('404')).toBeInTheDocument();
    expect(screen.getByText('Not Found')).toBeInTheDocument();
  });

  it('should render Body and Headers tabs', () => {
    renderWithProviders(<ResponseViewer response={mockSuccessResponse} />);
    expect(screen.getByText('Body')).toBeInTheDocument();
    expect(screen.getByText('Headers')).toBeInTheDocument();
  });

  it('should show headers count badge', () => {
    renderWithProviders(<ResponseViewer response={mockSuccessResponse} />);
    expect(screen.getByText('2')).toBeInTheDocument(); // 2 headers
  });

  it('should switch to headers tab and show header entries', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ResponseViewer response={mockSuccessResponse} />);
    await user.click(screen.getByText('Headers'));
    expect(screen.getByText('content-type:')).toBeInTheDocument();
    expect(screen.getByText('application/json')).toBeInTheDocument();
    expect(screen.getByText('x-request-id:')).toBeInTheDocument();
    expect(screen.getByText('req-123')).toBeInTheDocument();
  });

  it('should toggle between Pretty and Raw view', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ResponseViewer response={mockSuccessResponse} />);
    const toggleButton = screen.getByText('Raw');
    await user.click(toggleButton);
    expect(screen.getByText('Pretty')).toBeInTheDocument();
  });

  it('should render Copy button', () => {
    renderWithProviders(<ResponseViewer response={mockSuccessResponse} />);
    expect(screen.getByText('Copy')).toBeInTheDocument();
  });

  it('should show Copied! after Copy click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ResponseViewer response={mockSuccessResponse} />);
    expect(screen.getByText('Copy')).toBeInTheDocument();
    await user.click(screen.getByText('Copy'));
    expect(screen.getByText('Copied!')).toBeInTheDocument();
  });

  it('should not show timing breakdown when details are missing', () => {
    renderWithProviders(<ResponseViewer response={mock404Response} />);
    expect(screen.queryByText(/DNS:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/TCP:/)).not.toBeInTheDocument();
  });

  it('should handle string body response', () => {
    const stringResponse: ResponseData = {
      ...mockSuccessResponse,
      body: 'plain text response',
    };
    renderWithProviders(<ResponseViewer response={stringResponse} />);
    expect(screen.getByText('plain text response')).toBeInTheDocument();
  });
});
