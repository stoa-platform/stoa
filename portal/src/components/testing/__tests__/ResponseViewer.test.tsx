import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { ResponseViewer } from '../ResponseViewer';
import { renderWithProviders } from '../../../test/helpers';
import type { ResponseData } from '../ResponseViewer';

const makeResponse = (overrides: Partial<ResponseData> = {}): ResponseData => ({
  status: 200,
  statusText: 'OK',
  headers: { 'content-type': 'application/json', 'x-request-id': 'abc123' },
  body: { id: 1, name: 'order' },
  timing: { total: 150 },
  ...overrides,
});

describe('ResponseViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('empty state', () => {
    it('renders "No Response Yet" when response is null', () => {
      renderWithProviders(<ResponseViewer response={null} />);
      expect(screen.getByText('No Response Yet')).toBeInTheDocument();
    });

    it('renders instruction text', () => {
      renderWithProviders(<ResponseViewer response={null} />);
      expect(screen.getByText(/Configure your request above/)).toBeInTheDocument();
    });
  });

  describe('loading state', () => {
    it('renders "Sending request..." when isLoading=true', () => {
      renderWithProviders(<ResponseViewer response={null} isLoading={true} />);
      expect(screen.getByText('Sending request...')).toBeInTheDocument();
    });

    it('does not render empty state when loading', () => {
      renderWithProviders(<ResponseViewer response={null} isLoading={true} />);
      expect(screen.queryByText('No Response Yet')).not.toBeInTheDocument();
    });
  });

  describe('status display', () => {
    it('renders 200 OK status', () => {
      renderWithProviders(<ResponseViewer response={makeResponse()} />);
      expect(screen.getByText('200')).toBeInTheDocument();
      expect(screen.getByText('OK')).toBeInTheDocument();
    });

    it('renders 404 status', () => {
      renderWithProviders(
        <ResponseViewer response={makeResponse({ status: 404, statusText: 'Not Found' })} />
      );
      expect(screen.getByText('404')).toBeInTheDocument();
      expect(screen.getByText('Not Found')).toBeInTheDocument();
    });

    it('renders 500 status', () => {
      renderWithProviders(
        <ResponseViewer
          response={makeResponse({ status: 500, statusText: 'Internal Server Error' })}
        />
      );
      expect(screen.getByText('500')).toBeInTheDocument();
    });
  });

  describe('timing display', () => {
    it('renders timing in milliseconds', () => {
      renderWithProviders(<ResponseViewer response={makeResponse({ timing: { total: 150 } })} />);
      expect(screen.getByText('150ms')).toBeInTheDocument();
    });

    it('renders timing in seconds for large values', () => {
      renderWithProviders(<ResponseViewer response={makeResponse({ timing: { total: 1500 } })} />);
      expect(screen.getByText('1.50s')).toBeInTheDocument();
    });

    it('renders detailed timing when dns/tcp/ttfb present', () => {
      renderWithProviders(
        <ResponseViewer
          response={makeResponse({ timing: { total: 350, dns: 10, tcp: 40, ttfb: 100 } })}
        />
      );
      expect(screen.getByText(/DNS:/)).toBeInTheDocument();
      expect(screen.getByText(/TCP:/)).toBeInTheDocument();
      expect(screen.getByText(/TTFB:/)).toBeInTheDocument();
    });
  });

  describe('body tab', () => {
    it('renders body JSON by default', () => {
      renderWithProviders(<ResponseViewer response={makeResponse()} />);
      expect(screen.getByText(/"id": 1/)).toBeInTheDocument();
    });

    it('switches to raw view when Raw button is clicked', () => {
      renderWithProviders(<ResponseViewer response={makeResponse()} />);
      fireEvent.click(screen.getByRole('button', { name: 'Raw' }));
      expect(screen.getByRole('button', { name: 'Pretty' })).toBeInTheDocument();
    });

    it('switches back to pretty view when Pretty button is clicked', () => {
      renderWithProviders(<ResponseViewer response={makeResponse()} />);
      fireEvent.click(screen.getByRole('button', { name: 'Raw' }));
      fireEvent.click(screen.getByRole('button', { name: 'Pretty' }));
      expect(screen.getByRole('button', { name: 'Raw' })).toBeInTheDocument();
    });

    it('renders string body directly', () => {
      renderWithProviders(
        <ResponseViewer response={makeResponse({ body: 'plain text response' })} />
      );
      expect(screen.getByText('plain text response')).toBeInTheDocument();
    });
  });

  describe('headers tab', () => {
    it('shows header count badge', () => {
      renderWithProviders(<ResponseViewer response={makeResponse()} />);
      // "Headers 2" badge
      expect(screen.getByText('2')).toBeInTheDocument();
    });

    it('switches to headers view when Headers tab is clicked', () => {
      renderWithProviders(<ResponseViewer response={makeResponse()} />);
      fireEvent.click(screen.getByRole('button', { name: /Headers/ }));
      expect(screen.getByText('content-type:')).toBeInTheDocument();
      expect(screen.getByText('application/json')).toBeInTheDocument();
    });

    it('collapses headers when expand toggle is clicked', () => {
      renderWithProviders(<ResponseViewer response={makeResponse()} />);
      fireEvent.click(screen.getByRole('button', { name: /Headers/ }));
      // Click the expand toggle button that contains "Response Headers"
      const expandToggle = screen.getByRole('button', { name: /Response Headers/ });
      fireEvent.click(expandToggle);
      expect(screen.queryByText('content-type:')).not.toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('renders error message when response.error is set', () => {
      renderWithProviders(
        <ResponseViewer
          response={makeResponse({ error: 'Connection refused', status: 0, statusText: 'Error' })}
        />
      );
      expect(screen.getByText('Request Failed')).toBeInTheDocument();
      expect(screen.getByText('Connection refused')).toBeInTheDocument();
    });
  });

  describe('copy button', () => {
    it('renders Copy button', () => {
      renderWithProviders(<ResponseViewer response={makeResponse()} />);
      expect(screen.getByRole('button', { name: /Copy/ })).toBeInTheDocument();
    });
  });

  describe('body size', () => {
    it('renders body size in bytes', () => {
      renderWithProviders(<ResponseViewer response={makeResponse({ body: 'hello' })} />);
      // "5 B" for "hello"
      expect(screen.getByText(/\d+ B/)).toBeInTheDocument();
    });
  });
});
