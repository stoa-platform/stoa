import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SubscribeModal } from './SubscribeModal';
import type { API } from '../../types';

vi.mock('../../hooks/useApplications', () => ({
  useApplications: vi.fn(),
}));

vi.mock('./CertificateUploader', () => ({
  CertificateUploader: ({ required }: { required?: boolean }) => (
    <div data-testid="cert-uploader">{required ? 'required' : 'optional'}</div>
  ),
}));

import { useApplications } from '../../hooks/useApplications';

const mockApi: API = {
  id: 'api-1',
  name: 'Weather API',
  version: '2.0',
  description: 'Weather data',
  status: 'published',
  created_at: '2026-01-01T00:00:00Z',
};

const defaultProps = {
  isOpen: true,
  onClose: vi.fn(),
  onSubmit: vi.fn().mockResolvedValue(undefined),
  api: mockApi,
};

describe('SubscribeModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useApplications).mockReturnValue({
      data: {
        items: [
          { id: 'app-1', name: 'My App', status: 'active', created_at: '2026-01-01T00:00:00Z' },
          { id: 'app-2', name: 'Other App', status: 'active', created_at: '2026-01-01T00:00:00Z' },
        ],
        total: 2,
        page: 1,
        page_size: 20,
      },
      isLoading: false,
    } as ReturnType<typeof useApplications>);
  });

  it('should return null when not open', () => {
    const { container } = render(<SubscribeModal {...defaultProps} isOpen={false} />);
    expect(container.firstChild).toBeNull();
  });

  it('should show modal title with API name and version', () => {
    render(<SubscribeModal {...defaultProps} />);
    expect(screen.getByText('Subscribe to API')).toBeInTheDocument();
    expect(screen.getByText('Weather API v2.0')).toBeInTheDocument();
  });

  it('should show 4 plan options', () => {
    render(<SubscribeModal {...defaultProps} />);
    expect(screen.getByText('Free')).toBeInTheDocument();
    expect(screen.getByText('Basic')).toBeInTheDocument();
    expect(screen.getByText('Premium')).toBeInTheDocument();
    expect(screen.getByText('Enterprise')).toBeInTheDocument();
  });

  it('should show application dropdown', () => {
    render(<SubscribeModal {...defaultProps} />);
    expect(screen.getByText('Select an application...')).toBeInTheDocument();
  });

  it('should show applications in dropdown', () => {
    render(<SubscribeModal {...defaultProps} />);
    expect(screen.getByText('My App')).toBeInTheDocument();
    expect(screen.getByText('Other App')).toBeInTheDocument();
  });

  it('should show error message', () => {
    render(<SubscribeModal {...defaultProps} error="Subscription failed" />);
    expect(screen.getByText('Subscription failed')).toBeInTheDocument();
  });

  it('should show loading state', () => {
    render(<SubscribeModal {...defaultProps} isLoading={true} />);
    expect(screen.getByText('Subscribing...')).toBeInTheDocument();
  });

  it('should disable subscribe when no app selected', () => {
    render(<SubscribeModal {...defaultProps} />);
    const submitBtn = screen.getByText('Subscribe');
    expect(submitBtn).toBeDisabled();
  });

  it('should call onSubmit with form data', async () => {
    render(<SubscribeModal {...defaultProps} />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'app-1' } });
    fireEvent.click(screen.getByText('Premium'));
    fireEvent.click(screen.getByText('Subscribe'));

    await waitFor(() => {
      expect(defaultProps.onSubmit).toHaveBeenCalledWith({
        applicationId: 'app-1',
        applicationName: 'My App',
        apiId: 'api-1',
        plan: 'premium',
        certificateFingerprint: undefined,
      });
    });
  });

  it('should call onClose on Cancel', () => {
    render(<SubscribeModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Cancel'));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('should not close when loading', () => {
    render(<SubscribeModal {...defaultProps} isLoading={true} />);
    fireEvent.click(screen.getByText('Cancel'));
    expect(defaultProps.onClose).not.toHaveBeenCalled();
  });

  it('should show empty apps message when no active apps', () => {
    vi.mocked(useApplications).mockReturnValue({
      data: { items: [], total: 0, page: 1, page_size: 20 },
      isLoading: false,
    } as ReturnType<typeof useApplications>);

    render(<SubscribeModal {...defaultProps} />);
    expect(screen.getByText(/don't have any active applications/)).toBeInTheDocument();
  });

  it('should show apps loading state', () => {
    vi.mocked(useApplications).mockReturnValue({
      data: undefined,
      isLoading: true,
    } as ReturnType<typeof useApplications>);

    render(<SubscribeModal {...defaultProps} />);
    expect(screen.getByText('Loading applications...')).toBeInTheDocument();
  });

  it('should show certificate uploader for mTLS APIs', () => {
    const mtlsApi = { ...mockApi, tags: ['mtls'] };
    render(<SubscribeModal {...defaultProps} api={mtlsApi} />);
    expect(screen.getByTestId('cert-uploader')).toBeInTheDocument();
    expect(screen.getByText('Client Certificate')).toBeInTheDocument();
  });

  it('should not show certificate uploader for non-mTLS APIs', () => {
    render(<SubscribeModal {...defaultProps} />);
    expect(screen.queryByTestId('cert-uploader')).not.toBeInTheDocument();
  });

  it('should show info box', () => {
    render(<SubscribeModal {...defaultProps} />);
    expect(screen.getByText(/After subscribing, you can use your application/)).toBeInTheDocument();
  });
});
