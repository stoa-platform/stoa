import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createAuthMock } from '../../test/helpers';
import type { PersonaRole } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import { SkillPreview } from './SkillPreview';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockResolveSkills = vi.fn();

vi.mock('../../services/skillsApi', () => ({
  skillsService: {
    resolveSkills: (...args: unknown[]) => mockResolveSkills(...args),
  },
}));

function renderComponent() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SkillPreview />
    </QueryClientProvider>
  );
}

describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
  '%s persona',
  (role) => {
    beforeEach(() => {
      vi.clearAllMocks();
      vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
    });

    it('renders collapsed by default', () => {
      renderComponent();
      expect(screen.getByText('Resolution Preview')).toBeInTheDocument();
      expect(screen.queryByText('Tool Name')).not.toBeInTheDocument();
    });

    it('expands on click', async () => {
      renderComponent();
      fireEvent.click(screen.getByText('Resolution Preview'));
      expect(screen.getByText('Tool Name')).toBeInTheDocument();
      expect(screen.getByText('User Ref')).toBeInTheDocument();
      expect(screen.getByText('Resolve')).toBeInTheDocument();
    });

    it('collapses on second click', async () => {
      renderComponent();
      fireEvent.click(screen.getByText('Resolution Preview'));
      expect(screen.getByText('Tool Name')).toBeInTheDocument();
      fireEvent.click(screen.getByText('Resolution Preview'));
      expect(screen.queryByText('Tool Name')).not.toBeInTheDocument();
    });

    it('shows input fields when expanded', async () => {
      renderComponent();
      fireEvent.click(screen.getByText('Resolution Preview'));
      expect(screen.getByPlaceholderText('e.g. code-review')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('e.g. alice')).toBeInTheDocument();
    });

    it('calls resolveSkills on Resolve click', async () => {
      mockResolveSkills.mockResolvedValue([]);
      renderComponent();
      fireEvent.click(screen.getByText('Resolution Preview'));

      const user = userEvent.setup();
      await user.type(screen.getByPlaceholderText('e.g. code-review'), 'my-tool');
      fireEvent.click(screen.getByText('Resolve'));

      const expectedTenantId = createAuthMock(role).user?.tenant_id;
      await waitFor(() => {
        expect(mockResolveSkills).toHaveBeenCalledWith(expectedTenantId, 'my-tool', undefined);
      });
    });

    it('shows empty message when no skills match', async () => {
      mockResolveSkills.mockResolvedValue([]);
      renderComponent();
      fireEvent.click(screen.getByText('Resolution Preview'));
      fireEvent.click(screen.getByText('Resolve'));

      await waitFor(() => {
        expect(screen.getByText('No skills matched the given context.')).toBeInTheDocument();
      });
    });

    it('shows resolved skills in table', async () => {
      mockResolveSkills.mockResolvedValue([
        {
          name: 'Global Policy',
          scope: 'global',
          priority: 50,
          specificity: 0,
          instructions: 'Be nice',
        },
        {
          name: 'Team Review',
          scope: 'tenant',
          priority: 80,
          specificity: 1,
          instructions: 'Check tests',
        },
      ]);
      renderComponent();
      fireEvent.click(screen.getByText('Resolution Preview'));
      fireEvent.click(screen.getByText('Resolve'));

      await waitFor(() => {
        expect(screen.getByText('Global Policy')).toBeInTheDocument();
      });
      expect(screen.getByText('Team Review')).toBeInTheDocument();
      expect(screen.getByText('Merged Instructions')).toBeInTheDocument();
    });
  }
);
