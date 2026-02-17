import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import {
  createAuthMock,
  renderWithProviders,
  mockWorkflowTemplate,
  mockWorkflowInstance,
} from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

// Mock AuthContext
vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

// Mock api service
const mockListTemplates = vi
  .fn()
  .mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
const mockCreateTemplate = vi.fn().mockResolvedValue({});
const mockUpdateTemplate = vi.fn().mockResolvedValue({});
const mockDeleteTemplate = vi.fn().mockResolvedValue(undefined);
const mockListInstances = vi
  .fn()
  .mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
const mockStartWorkflow = vi.fn().mockResolvedValue({});
const mockApproveStep = vi.fn().mockResolvedValue({});
const mockRejectStep = vi.fn().mockResolvedValue({});

vi.mock('../services/api', () => ({
  apiService: {
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
    listWorkflowTemplates: (...args: unknown[]) => mockListTemplates(...args),
    createWorkflowTemplate: (...args: unknown[]) => mockCreateTemplate(...args),
    updateWorkflowTemplate: (...args: unknown[]) => mockUpdateTemplate(...args),
    deleteWorkflowTemplate: (...args: unknown[]) => mockDeleteTemplate(...args),
    listWorkflowInstances: (...args: unknown[]) => mockListInstances(...args),
    startWorkflow: (...args: unknown[]) => mockStartWorkflow(...args),
    approveWorkflowStep: (...args: unknown[]) => mockApproveStep(...args),
    rejectWorkflowStep: (...args: unknown[]) => mockRejectStep(...args),
  },
}));

// Mock config
vi.mock('../config', () => ({
  config: {
    api: { baseUrl: 'https://api.gostoa.dev' },
    services: {
      gitlab: { url: 'https://gitlab.example.com' },
      awx: {
        url: 'https://awx.example.com',
        getJobUrl: (id: string) => `https://awx.example.com/#/jobs/${id}`,
      },
    },
  },
}));

import { Workflows } from './Workflows';

function renderComponent() {
  return renderWithProviders(<Workflows />, { route: '/workflows' });
}

describe('Workflows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockListTemplates.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    mockListInstances.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
  });

  it('renders the page heading', () => {
    renderComponent();
    expect(screen.getByRole('heading', { name: 'Onboarding Workflows' })).toBeInTheDocument();
  });

  it('renders the subtitle', () => {
    renderComponent();
    expect(
      screen.getByText(
        'Manage approval workflows for user registration, consumer onboarding, and tenant setup.'
      )
    ).toBeInTheDocument();
  });

  it('renders both tab buttons', () => {
    renderComponent();
    expect(screen.getByText('Templates')).toBeInTheDocument();
    expect(screen.getByText('Instances')).toBeInTheDocument();
  });

  it('shows Templates tab by default', async () => {
    renderComponent();
    await waitFor(() => {
      expect(mockListTemplates).toHaveBeenCalledWith('gregarious-games');
    });
  });

  it('switches to Instances tab', async () => {
    renderComponent();
    fireEvent.click(screen.getByText('Instances'));
    await waitFor(() => {
      expect(mockListInstances).toHaveBeenCalled();
    });
  });

  // 4-persona page render
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        expect(screen.getByRole('heading', { name: 'Onboarding Workflows' })).toBeInTheDocument();
      });
    }
  );
});

describe('TemplatesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockListTemplates.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    mockListInstances.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
  });

  it('shows empty state when no templates', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('No workflow templates yet.')).toBeInTheDocument();
    });
  });

  it('shows template count label', async () => {
    mockListTemplates.mockResolvedValue({
      items: [
        mockWorkflowTemplate(),
        mockWorkflowTemplate({ id: 'wftpl-2', name: 'Second Template' }),
      ],
      total: 2,
      page: 1,
      page_size: 20,
    });
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('2 templates')).toBeInTheDocument();
    });
  });

  it('renders template rows with name, type, and mode', async () => {
    mockListTemplates.mockResolvedValue({
      items: [
        mockWorkflowTemplate({
          name: 'Enterprise Approval',
          workflow_type: 'user_registration',
          mode: 'approval_chain',
        }),
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Enterprise Approval')).toBeInTheDocument();
    });
    expect(screen.getByText('User Registration')).toBeInTheDocument();
    expect(screen.getByText('Chain')).toBeInTheDocument();
  });

  it('shows Refresh button', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Refresh')).toBeInTheDocument();
    });
  });

  it('shows error state on API failure', async () => {
    mockListTemplates.mockRejectedValue(new Error('Network error'));
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  // 4-persona RBAC: delete button visibility
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona — delete button',
    (role) => {
      it(`${['cpi-admin', 'tenant-admin'].includes(role) ? 'shows' : 'hides'} delete button`, async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        mockListTemplates.mockResolvedValue({
          items: [mockWorkflowTemplate()],
          total: 1,
          page: 1,
          page_size: 20,
        });
        renderComponent();
        await waitFor(() => {
          expect(screen.getByText('Default User Onboarding')).toBeInTheDocument();
        });
        if (['cpi-admin', 'tenant-admin'].includes(role)) {
          expect(screen.getByTitle('Delete template')).toBeInTheDocument();
        } else {
          expect(screen.queryByTitle('Delete template')).not.toBeInTheDocument();
        }
      });
    }
  );
});

describe('InstancesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockListTemplates.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    mockListInstances.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
  });

  async function switchToInstances() {
    renderComponent();
    fireEvent.click(screen.getByText('Instances'));
    await waitFor(() => {
      expect(mockListInstances).toHaveBeenCalled();
    });
  }

  it('shows empty state when no instances', async () => {
    await switchToInstances();
    await waitFor(() => {
      expect(screen.getByText('No workflow instances found.')).toBeInTheDocument();
    });
  });

  it('renders instance rows with email and status', async () => {
    mockListInstances.mockResolvedValue({
      items: [mockWorkflowInstance({ subject_email: 'alice@example.com', status: 'approved' })],
      total: 1,
      page: 1,
      page_size: 20,
    });
    await switchToInstances();
    await waitFor(() => {
      expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    });
    expect(screen.getByText('User Registration')).toBeInTheDocument();
  });

  it('renders status filter dropdown', async () => {
    await switchToInstances();
    expect(screen.getByText('All statuses')).toBeInTheDocument();
  });

  it('shows error state on API failure', async () => {
    mockListInstances.mockRejectedValue(new Error('Server error'));
    await switchToInstances();
    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument();
    });
  });

  // 4-persona RBAC: approve/reject button visibility
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona — approve/reject buttons',
    (role) => {
      it(`${['cpi-admin', 'tenant-admin'].includes(role) ? 'shows' : 'hides'} approve/reject`, async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        mockListInstances.mockResolvedValue({
          items: [mockWorkflowInstance({ status: 'pending' })],
          total: 1,
          page: 1,
          page_size: 20,
        });
        renderComponent();
        fireEvent.click(screen.getByText('Instances'));
        await waitFor(() => {
          expect(screen.getByText('newuser@example.com')).toBeInTheDocument();
        });
        if (['cpi-admin', 'tenant-admin'].includes(role)) {
          expect(screen.getByTitle('Approve')).toBeInTheDocument();
          expect(screen.getByTitle('Reject')).toBeInTheDocument();
        } else {
          expect(screen.queryByTitle('Approve')).not.toBeInTheDocument();
          expect(screen.queryByTitle('Reject')).not.toBeInTheDocument();
        }
      });
    }
  );

  it('hides approve/reject for completed instances', async () => {
    mockListInstances.mockResolvedValue({
      items: [mockWorkflowInstance({ status: 'completed' })],
      total: 1,
      page: 1,
      page_size: 20,
    });
    await switchToInstances();
    await waitFor(() => {
      expect(screen.getByText('newuser@example.com')).toBeInTheDocument();
    });
    expect(screen.queryByTitle('Approve')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Reject')).not.toBeInTheDocument();
  });
});
