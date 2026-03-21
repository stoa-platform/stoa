import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SubscribeModal } from './SubscribeModal';
import type { API } from '../../types';

vi.mock('../../hooks/useApplications', () => ({
  useApplications: vi.fn(),
  useCreateApplication: vi.fn(),
}));

vi.mock('./CertificateUploader', () => ({
  CertificateUploader: ({ required }: { required?: boolean }) => (
    <div data-testid="cert-uploader">{required ? 'required' : 'optional'}</div>
  ),
}));

import { useApplications, useCreateApplication } from '../../hooks/useApplications';

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

const mockMutateAsync = vi.fn().mockResolvedValue({ id: 'new-app-id', name: 'My New App' });

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
    vi.mocked(useCreateApplication).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as ReturnType<typeof useCreateApplication>);
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

  it('should show empty dropdown with no active apps', () => {
    vi.mocked(useApplications).mockReturnValue({
      data: { items: [], total: 0, page: 1, page_size: 20 },
      isLoading: false,
    } as ReturnType<typeof useApplications>);

    render(<SubscribeModal {...defaultProps} />);
    // Dropdown shows only the placeholder option; Subscribe stays disabled
    expect(screen.getByText('Select an application...')).toBeInTheDocument();
    expect(screen.getByText('Subscribe')).toBeDisabled();
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

  // ── CAB-1907: Inline app creation ──────────────────────────────────────────

  describe('inline app creation (CAB-1907)', () => {
    it('should show "Create new application" button below the app dropdown', () => {
      render(<SubscribeModal {...defaultProps} />);
      expect(screen.getByText('Create new application')).toBeInTheDocument();
    });

    it('should show inline form when "Create new application" is clicked', () => {
      render(<SubscribeModal {...defaultProps} />);
      fireEvent.click(screen.getByText('Create new application'));

      expect(screen.getByLabelText(/application name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/security profile/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Create' })).toBeInTheDocument();
      // Two Cancel buttons exist (inline form + modal footer) — both should be present
      expect(screen.getAllByRole('button', { name: 'Cancel' })).toHaveLength(2);
    });

    it('should hide the app dropdown while the inline form is visible', () => {
      render(<SubscribeModal {...defaultProps} />);
      fireEvent.click(screen.getByText('Create new application'));

      expect(screen.queryByText('Select an application...')).not.toBeInTheDocument();
    });

    it('should show three security profile options', () => {
      render(<SubscribeModal {...defaultProps} />);
      fireEvent.click(screen.getByText('Create new application'));

      const profileSelect = screen.getByLabelText(/security profile/i);
      expect(profileSelect).toBeInTheDocument();
      // Check all three options are present
      expect(screen.getByText('OAuth2 Public (PKCE)')).toBeInTheDocument();
      expect(screen.getByText('OAuth2 Confidential')).toBeInTheDocument();
      expect(screen.getByText('API Key')).toBeInTheDocument();
    });

    it('should keep Create button disabled when app name is empty', () => {
      render(<SubscribeModal {...defaultProps} />);
      fireEvent.click(screen.getByText('Create new application'));

      expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled();
    });

    it('should enable Create button when app name is non-empty', () => {
      render(<SubscribeModal {...defaultProps} />);
      fireEvent.click(screen.getByText('Create new application'));

      fireEvent.change(screen.getByLabelText(/application name/i), {
        target: { value: 'My New App' },
      });

      expect(screen.getByRole('button', { name: 'Create' })).not.toBeDisabled();
    });

    it('should dismiss inline form and restore dropdown on Cancel', () => {
      render(<SubscribeModal {...defaultProps} />);
      fireEvent.click(screen.getByText('Create new application'));
      fireEvent.change(screen.getByLabelText(/application name/i), {
        target: { value: 'Temp' },
      });

      // Click the first Cancel (inline form), not the footer Cancel
      fireEvent.click(screen.getAllByRole('button', { name: 'Cancel' })[0]);

      // Dropdown is back, form is gone
      expect(screen.getByText('Select an application...')).toBeInTheDocument();
      expect(screen.queryByLabelText(/application name/i)).not.toBeInTheDocument();
    });

    it('should call useCreateApplication with correct payload on Create', async () => {
      render(<SubscribeModal {...defaultProps} />);
      fireEvent.click(screen.getByText('Create new application'));

      fireEvent.change(screen.getByLabelText(/application name/i), {
        target: { value: 'My New App' },
      });
      fireEvent.change(screen.getByLabelText(/security profile/i), {
        target: { value: 'api_key' },
      });

      fireEvent.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({
          name: 'My New App',
          display_name: 'My New App',
          redirect_uris: [],
          security_profile: 'api_key',
        });
      });
    });

    it('should auto-select the newly created app and hide the inline form on success', async () => {
      mockMutateAsync.mockResolvedValueOnce({ id: 'new-app-id', name: 'My New App' });

      render(<SubscribeModal {...defaultProps} />);
      fireEvent.click(screen.getByText('Create new application'));
      fireEvent.change(screen.getByLabelText(/application name/i), {
        target: { value: 'My New App' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() => {
        // Inline form is dismissed — dropdown is restored
        expect(screen.queryByLabelText(/application name/i)).not.toBeInTheDocument();
      });
    });

    it('should display an error message when app creation fails', async () => {
      mockMutateAsync.mockRejectedValueOnce(new Error('Name already taken'));

      render(<SubscribeModal {...defaultProps} />);
      fireEvent.click(screen.getByText('Create new application'));
      fireEvent.change(screen.getByLabelText(/application name/i), {
        target: { value: 'Duplicate App' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() => {
        expect(screen.getByText('Name already taken')).toBeInTheDocument();
      });
    });

    it('should reset inline form state when modal is reopened', async () => {
      const { rerender } = render(<SubscribeModal {...defaultProps} />);
      fireEvent.click(screen.getByText('Create new application'));
      fireEvent.change(screen.getByLabelText(/application name/i), {
        target: { value: 'Half-typed name' },
      });

      // Close then reopen the modal
      rerender(<SubscribeModal {...defaultProps} isOpen={false} />);
      rerender(<SubscribeModal {...defaultProps} isOpen={true} />);

      // Inline form should be hidden again
      expect(screen.queryByLabelText(/application name/i)).not.toBeInTheDocument();
      expect(screen.getByText('Select an application...')).toBeInTheDocument();
    });
  });
});
