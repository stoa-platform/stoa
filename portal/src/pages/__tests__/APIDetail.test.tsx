/**
 * Tests for APIDetail page (CAB-1133)
 *
 * Displays detailed information about an API including OpenAPI spec, endpoints, and subscription options.
 * Page-level functional tests covering all personas.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { APIDetail } from '../apis/APIDetail';
import { renderWithProviders, createAuthMock, mockAPI } from '../../test/helpers';

// Mock hooks
const mockUseAPI = vi.fn();
const mockUseOpenAPISpec = vi.fn();
const mockUseSubscribe = vi.fn();

vi.mock('../../hooks/useAPIs', () => ({
  useAPI: (id: string | undefined) => mockUseAPI(id),
  useOpenAPISpec: (id: string | undefined) => mockUseOpenAPISpec(id),
}));

vi.mock('../../hooks/useSubscriptions', () => ({
  useSubscribe: () => mockUseSubscribe(),
  SubscribeToAPIResponse: {},
}));

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock config
vi.mock('../../config', () => ({
  config: {
    features: {
      enableSubscriptions: true,
      enableAPITesting: true,
    },
  },
}));

// Mock SubscribeModal as stub
vi.mock('../../components/subscriptions/SubscribeModal', () => ({
  SubscribeModal: () => <div data-testid="subscribe-modal">Subscribe Modal</div>,
}));

describe('APIDetail', () => {
  const mockAPIData = mockAPI({
    id: 'api-1',
    name: 'Payment API',
    version: '2.1.0',
    status: 'published',
    description: 'Process payments securely',
    category: 'Finance',
    tags: ['payments', 'fintech'],
    endpoints: [
      {
        path: '/v1/payments',
        method: 'POST',
        summary: 'Create payment',
        parameters: [],
        responses: { '200': { description: 'Payment created' } },
      },
      {
        path: '/v1/payments/{id}',
        method: 'GET',
        summary: 'Get payment',
        parameters: [{ name: 'id', in: 'path', required: true, description: 'Payment ID' }],
        responses: { '200': { description: 'Payment details' } },
      },
    ],
  });

  const mockOpenAPISpecData = {
    openapi: '3.0.0',
    info: { title: 'Payment API', version: '2.1.0' },
    paths: {},
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));
    mockUseAPI.mockReturnValue({
      data: mockAPIData,
      isLoading: false,
      isError: false,
      error: null,
    });
    mockUseOpenAPISpec.mockReturnValue({
      data: mockOpenAPISpecData,
      isLoading: false,
    });
    mockUseSubscribe.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    });
  });

  describe('Loading State', () => {
    it('should show loading spinner when API details are loading', () => {
      mockUseAPI.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
        error: null,
      });

      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.getByText('Loading API details...')).toBeInTheDocument();
    });
  });

  describe('Error State', () => {
    it('should show error message when API fetch fails', () => {
      mockUseAPI.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: new Error('API not found'),
      });

      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.getByText('Failed to load API')).toBeInTheDocument();
      expect(screen.getByText('API not found')).toBeInTheDocument();
    });

    it('should show return to catalog link on error', () => {
      mockUseAPI.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: new Error('API not found'),
      });

      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.getByText('Return to Catalog')).toBeInTheDocument();
    });
  });

  describe('Data Renders', () => {
    it('should render API name and version', () => {
      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.getByText('Payment API')).toBeInTheDocument();
      expect(screen.getByText('Version 2.1.0')).toBeInTheDocument();
    });

    it('should render status badge', () => {
      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.getByText('published')).toBeInTheDocument();
    });

    it('should render description', () => {
      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      // Description appears multiple times (header + overview tab), so check it exists
      const descriptions = screen.getAllByText('Process payments securely');
      expect(descriptions.length).toBeGreaterThan(0);
    });

    it('should render category and tags', () => {
      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.getByText('Finance')).toBeInTheDocument();
      expect(screen.getByText('payments')).toBeInTheDocument();
      expect(screen.getByText('fintech')).toBeInTheDocument();
    });

    it('should render back to catalog link', () => {
      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.getByText('Back to API Catalog')).toBeInTheDocument();
    });
  });

  describe('Tabs', () => {
    it('should render all 3 tabs', () => {
      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.getByRole('button', { name: /Overview/ })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Endpoints/ })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /OpenAPI Spec/ })).toBeInTheDocument();
    });

    it('should show Overview tab content by default', () => {
      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.getByText('About this API')).toBeInTheDocument();
      expect(screen.getByText('Quick Start')).toBeInTheDocument();
    });

    it('should show endpoints tab content when clicked', async () => {
      const user = userEvent.setup();
      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      await user.click(screen.getByRole('button', { name: /Endpoints/ }));

      // Check for endpoint methods
      expect(screen.getByText('POST')).toBeInTheDocument();
      expect(screen.getByText('GET')).toBeInTheDocument();
      // Check for endpoint paths
      expect(screen.getByText('/v1/payments')).toBeInTheDocument();
      expect(screen.getByText('/v1/payments/{id}')).toBeInTheDocument();
    });

    it('should show OpenAPI spec tab content when clicked', async () => {
      const user = userEvent.setup();
      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      await user.click(screen.getByRole('button', { name: /OpenAPI Spec/ }));

      expect(screen.getByText('OpenAPI Specification')).toBeInTheDocument();
      expect(screen.getByText(/openapi/)).toBeInTheDocument();
    });
  });

  describe('Endpoints Tab', () => {
    it('should list all endpoints', async () => {
      const user = userEvent.setup();
      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      await user.click(screen.getByRole('button', { name: /Endpoints/ }));

      expect(screen.getByText('/v1/payments')).toBeInTheDocument();
      expect(screen.getByText('/v1/payments/{id}')).toBeInTheDocument();
    });
  });

  describe('OpenAPI Spec Tab', () => {
    it('should show copy button', async () => {
      const user = userEvent.setup();
      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      await user.click(screen.getByRole('button', { name: /OpenAPI Spec/ }));

      // Look for Copy button (not the one in the header that says "Copy")
      const copyButtons = screen.getAllByText('Copy');
      expect(copyButtons.length).toBeGreaterThan(0);
    });

    it('should show spec JSON', async () => {
      const user = userEvent.setup();
      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      await user.click(screen.getByRole('button', { name: /OpenAPI Spec/ }));

      // Check for JSON content in the spec
      expect(screen.getByText(/"openapi": "3.0.0"/)).toBeInTheDocument();
    });
  });

  describe('Subscribe Button', () => {
    it('should show subscribe button when enableSubscriptions=true and status=published', () => {
      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.getByText('Subscribe')).toBeInTheDocument();
    });

    it('should not show subscribe button when status=draft', () => {
      mockUseAPI.mockReturnValue({
        data: { ...mockAPIData, status: 'draft' },
        isLoading: false,
        isError: false,
        error: null,
      });

      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.queryByText('Subscribe')).not.toBeInTheDocument();
    });
  });

  describe('Try API Link', () => {
    it('should show try this API link when enableAPITesting=true', () => {
      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.getByText('Try this API')).toBeInTheDocument();
    });
  });

  describe('Persona-based Tests', () => {
    it('should render for cpi-admin', () => {
      mockUseAuth.mockReturnValue(createAuthMock('cpi-admin'));

      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.getByText('Payment API')).toBeInTheDocument();
    });

    it('should render for tenant-admin', () => {
      mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));

      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.getByText('Payment API')).toBeInTheDocument();
    });

    it('should render for devops', () => {
      mockUseAuth.mockReturnValue(createAuthMock('devops'));

      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.getByText('Payment API')).toBeInTheDocument();
    });

    it('should render for viewer', () => {
      mockUseAuth.mockReturnValue(createAuthMock('viewer'));

      renderWithProviders(<APIDetail />, { route: '/apis/api-1' });

      expect(screen.getByText('Payment API')).toBeInTheDocument();
    });
  });
});
