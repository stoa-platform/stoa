import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

// Mock skills service
const mockListSkills = vi.fn().mockResolvedValue([
  {
    key: 'ns/code-review',
    name: 'Code Review',
    description: 'Reviews code for best practices',
    tenant_id: 'tenant-1',
    scope: 'tenant',
    priority: 80,
    instructions: 'Review code carefully',
    tool_ref: null,
    user_ref: null,
    enabled: true,
  },
  {
    key: 'ns/security',
    name: 'Security Scanner',
    description: null,
    tenant_id: 'tenant-1',
    scope: 'global',
    priority: 50,
    instructions: 'Check for vulnerabilities',
    tool_ref: null,
    user_ref: null,
    enabled: false,
  },
]);

vi.mock('../../services/skillsApi', () => ({
  skillsService: {
    listSkills: (...args: unknown[]) => mockListSkills(...args),
    upsertSkill: vi.fn().mockResolvedValue({ key: 'test' }),
    deleteSkill: vi.fn().mockResolvedValue(undefined),
  },
}));

// Mock shared components
vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(false), () => null],
}));

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title?: string }) => <div data-testid="empty-state">{title}</div>,
}));

// Mock modal
vi.mock('./SkillFormModal', () => ({
  SkillFormModal: () => <div data-testid="skill-modal">Skill Modal</div>,
}));

import { SkillsList } from './SkillsList';

function renderComponent() {
  return renderWithProviders(<SkillsList />, { route: '/skills' });
}

describe('SkillsList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockListSkills.mockResolvedValue([
      {
        key: 'ns/code-review',
        name: 'Code Review',
        description: 'Reviews code for best practices',
        tenant_id: 'tenant-1',
        scope: 'tenant',
        priority: 80,
        instructions: 'Review code carefully',
        tool_ref: null,
        user_ref: null,
        enabled: true,
      },
      {
        key: 'ns/security',
        name: 'Security Scanner',
        description: null,
        tenant_id: 'tenant-1',
        scope: 'global',
        priority: 50,
        instructions: 'Check for vulnerabilities',
        tool_ref: null,
        user_ref: null,
        enabled: false,
      },
    ]);
  });

  it('renders the heading', async () => {
    renderComponent();
    expect(await screen.findByRole('heading', { name: 'Skills' })).toBeInTheDocument();
  });

  it('renders the subtitle', async () => {
    renderComponent();
    expect(
      await screen.findByText(/Manage agent skill instructions using the CSS cascade model/)
    ).toBeInTheDocument();
  });

  it('shows skills after loading', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Code Review')).toBeInTheDocument();
    });
    expect(screen.getByText('Security Scanner')).toBeInTheDocument();
  });

  it('shows scope badges', async () => {
    renderComponent();
    await waitFor(() => {
      // "Tenant" appears as both a column header and scope badge, so use getAllByText
      expect(screen.getAllByText('Tenant').length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getAllByText('Global').length).toBeGreaterThanOrEqual(1);
  });

  it('shows enabled/disabled status', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Enabled')).toBeInTheDocument();
    });
    expect(screen.getByText('Disabled')).toBeInTheDocument();
  });

  it('shows cascade legend', async () => {
    renderComponent();
    expect(await screen.findByText('Cascade order:')).toBeInTheDocument();
  });

  it('shows empty state when no skills', async () => {
    mockListSkills.mockResolvedValue([]);
    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  it('shows error message on failure', async () => {
    mockListSkills.mockRejectedValue(new Error('Network error'));
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        expect(await screen.findByRole('heading', { name: 'Skills' })).toBeInTheDocument();
      });

      if (role === 'cpi-admin' || role === 'tenant-admin') {
        it('shows Add Skill button', async () => {
          vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
          renderComponent();
          expect(await screen.findByText('Add Skill')).toBeInTheDocument();
        });
      }

      if (role === 'devops' || role === 'viewer') {
        it('hides Add Skill button', async () => {
          vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
          renderComponent();
          await waitFor(() => {
            expect(screen.getByText('Code Review')).toBeInTheDocument();
          });
          expect(screen.queryByText('Add Skill')).not.toBeInTheDocument();
        });
      }
    }
  );
});
