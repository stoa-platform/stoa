/**
 * APIComparePage Tests - CAB-1470
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../test/helpers';
import { APIComparePage } from '../api-compare/APIComparePage';

const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('../../i18n', () => ({
  loadNamespace: vi.fn(),
  LANGUAGE_KEY: 'stoa:language',
}));

vi.mock('../../config', () => ({
  config: {
    features: { enableI18n: false },
  },
}));

const mockComparisonData = vi.fn();

vi.mock('../../hooks/useAPIComparison', () => ({
  useAPIComparison: () => ({
    data: mockComparisonData(),
    isLoading: false,
    isFetching: false,
  }),
}));

describe('APIComparePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('cpi-admin'));
    mockComparisonData.mockReturnValue(null);
  });

  it('renders the page heading and subtitle', async () => {
    renderWithProviders(<APIComparePage />);
    await waitFor(() => {
      expect(screen.getByText('Compare APIs')).toBeInTheDocument();
    });
    expect(screen.getByText('Side-by-side comparison of API capabilities')).toBeInTheDocument();
  });

  it('shows pre-select empty state', async () => {
    renderWithProviders(<APIComparePage />);
    await waitFor(() => {
      expect(screen.getByText('Select at least 2 APIs to compare')).toBeInTheDocument();
    });
    expect(
      screen.getByText('Add API IDs above to see a side-by-side feature comparison')
    ).toBeInTheDocument();
  });

  it('renders API input field', async () => {
    renderWithProviders(<APIComparePage />);
    await waitFor(() => {
      expect(screen.getByPlaceholderText('Enter API ID to compare...')).toBeInTheDocument();
    });
  });

  it('renders Add button', async () => {
    renderWithProviders(<APIComparePage />);
    await waitFor(() => {
      expect(screen.getByText('Add')).toBeInTheDocument();
    });
  });

  it('shows selected count', async () => {
    renderWithProviders(<APIComparePage />);
    await waitFor(() => {
      expect(screen.getByText(/0\/5 selected/)).toBeInTheDocument();
    });
  });

  it('adds API ID on button click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<APIComparePage />);
    const input = screen.getByPlaceholderText('Enter API ID to compare...');
    await user.type(input, 'api-1');
    await user.click(screen.getByText('Add'));
    await waitFor(() => {
      expect(screen.getByText('api-1')).toBeInTheDocument();
    });
    expect(screen.getByText(/1\/5 selected/)).toBeInTheDocument();
  });

  it('adds API ID on Enter key', async () => {
    const user = userEvent.setup();
    renderWithProviders(<APIComparePage />);
    const input = screen.getByPlaceholderText('Enter API ID to compare...');
    await user.type(input, 'api-2{enter}');
    await waitFor(() => {
      expect(screen.getByText('api-2')).toBeInTheDocument();
    });
  });

  it('removes API ID on chip close click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<APIComparePage />);
    const input = screen.getByPlaceholderText('Enter API ID to compare...');
    await user.type(input, 'api-1{enter}');
    await waitFor(() => {
      expect(screen.getByText('api-1')).toBeInTheDocument();
    });
    // Click the X button inside the chip
    const chipContainer = screen.getByText('api-1').closest('span');
    const closeButton = chipContainer?.querySelector('button');
    if (closeButton) await user.click(closeButton);
    await waitFor(() => {
      expect(screen.queryByText('api-1')).not.toBeInTheDocument();
    });
  });

  it('prevents duplicate API IDs', async () => {
    const user = userEvent.setup();
    renderWithProviders(<APIComparePage />);
    const input = screen.getByPlaceholderText('Enter API ID to compare...');
    await user.type(input, 'api-1{enter}');
    await waitFor(() => {
      expect(screen.getByText('api-1')).toBeInTheDocument();
    });
    await user.type(input, 'api-1{enter}');
    // Should still only have 1 chip
    expect(screen.getByText(/1\/5 selected/)).toBeInTheDocument();
  });

  it('returns null when not authenticated', () => {
    mockAuth.mockReturnValue({
      ...createAuthMock('cpi-admin'),
      isAuthenticated: false,
      isLoading: false,
    });
    const { container } = renderWithProviders(<APIComparePage />);
    expect(container.innerHTML).toBe('');
  });

  describe('Persona-based Tests', () => {
    const personas: PersonaRole[] = ['cpi-admin', 'tenant-admin', 'devops', 'viewer'];

    it.each(personas)('%s can access compare APIs page (stoa:catalog:read)', async (persona) => {
      mockAuth.mockReturnValue(createAuthMock(persona));
      renderWithProviders(<APIComparePage />);
      await waitFor(() => {
        expect(screen.getByText('Compare APIs')).toBeInTheDocument();
      });
    });
  });
});
