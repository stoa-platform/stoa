/**
 * MyApplications Tests - CAB-1167
 *
 * Tests for the applications management page with create, list, and credentials display.
 */

import { screen, waitFor } from '@testing-library/react';
import {
  renderWithProviders,
  createAuthMock,
  mockApplication,
  type PersonaRole,
} from '../../test/helpers';
import { MyApplications } from '../apps/MyApplications';

// Mock i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

// Mock AuthContext at module level
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

// Mock useApplications hook
const mockApplicationsData = vi.fn();
const mockRefetch = vi.fn();
const mockCreateMutation = vi.fn();

vi.mock('../../hooks/useApplications', () => ({
  useApplications: () => ({
    data: mockApplicationsData(),
    isLoading: false,
    isError: false,
    error: null,
    refetch: mockRefetch,
  }),
  useCreateApplication: () => ({
    mutateAsync: mockCreateMutation,
    isPending: false,
  }),
}));

// Mock components
vi.mock('../../components/apps/ApplicationCard', () => ({
  ApplicationCard: ({ application }: { application: unknown }) => (
    <div data-testid={`app-card-${(application as { id: string }).id}`}>
      {(application as { name: string }).name}
    </div>
  ),
}));

vi.mock('../../components/apps/CreateAppModal', () => ({
  CreateAppModal: ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) =>
    isOpen ? (
      <div data-testid="create-app-modal">
        <button onClick={onClose}>Close</button>
      </div>
    ) : null,
}));

vi.mock('../../components/apps/CredentialsViewer', () => ({
  CredentialsViewer: ({ clientId }: { clientId: string }) => (
    <div data-testid="credentials-viewer">{clientId}</div>
  ),
}));

describe('MyApplications', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    mockApplicationsData.mockReturnValue({ items: [] });
  });

  it('renders the page heading', () => {
    renderWithProviders(<MyApplications />);
    expect(screen.getByText('title')).toBeInTheDocument();
  });

  it('renders Create Application button', () => {
    renderWithProviders(<MyApplications />);
    expect(screen.getByText('createApp')).toBeInTheDocument();
  });

  it('shows empty state when no applications exist', () => {
    renderWithProviders(<MyApplications />);
    expect(screen.getByText('empty.title')).toBeInTheDocument();
    expect(screen.getByText('empty.createFirst')).toBeInTheDocument();
  });

  it('renders applications when data exists', () => {
    mockApplicationsData.mockReturnValue({
      items: [
        mockApplication({ id: 'app-1', name: 'App 1' }),
        mockApplication({ id: 'app-2', name: 'App 2' }),
      ],
    });

    renderWithProviders(<MyApplications />);

    expect(screen.getByTestId('app-card-app-1')).toBeInTheDocument();
    expect(screen.getByTestId('app-card-app-2')).toBeInTheDocument();
    expect(screen.getByText('count')).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      beforeEach(() => {
        vi.clearAllMocks();
        mockAuth.mockReturnValue(createAuthMock(role));
        mockApplicationsData.mockReturnValue({ items: [] });
      });

      it('renders the page without error', async () => {
        renderWithProviders(<MyApplications />);
        await waitFor(() => {
          expect(screen.getByText('title')).toBeInTheDocument();
        });
      });

      it('shows empty state', () => {
        renderWithProviders(<MyApplications />);
        expect(screen.getByText('empty.title')).toBeInTheDocument();
      });
    }
  );
});
