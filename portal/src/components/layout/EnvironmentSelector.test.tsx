import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { EnvironmentSelector } from './EnvironmentSelector';
import { renderWithProviders, createAuthMock } from '../../test/helpers';

const mockSwitchEnvironment = vi.fn();
const mockPortalEnvironment = vi.fn();

vi.mock('../../contexts/EnvironmentContext', () => ({
  usePortalEnvironment: () => mockPortalEnvironment(),
}));

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => createAuthMock('cpi-admin'),
}));

function makeEnvContext(activeEnv = 'dev') {
  return {
    activeEnvironment: activeEnv,
    activeConfig:
      activeEnv === 'prod'
        ? { name: 'prod', label: 'Production', mode: 'read-only', color: 'red' }
        : { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
    environments: [
      { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
      { name: 'staging', label: 'Staging', mode: 'full', color: 'amber' },
      { name: 'prod', label: 'Production', mode: 'read-only', color: 'red' },
    ],
    endpoints: null,
    switchEnvironment: mockSwitchEnvironment,
    loading: false,
    error: null,
  };
}

describe('EnvironmentSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPortalEnvironment.mockReturnValue(makeEnvContext());
  });

  it('renders the active environment label', () => {
    renderWithProviders(<EnvironmentSelector />);
    expect(screen.getByText('Development')).toBeInTheDocument();
  });

  it('opens dropdown on click', () => {
    renderWithProviders(<EnvironmentSelector />);
    fireEvent.click(screen.getByRole('button', { name: /environment/i }));
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(screen.getByText('Staging')).toBeInTheDocument();
    expect(screen.getByText('Production')).toBeInTheDocument();
  });

  it('calls switchEnvironment when selecting a different env', () => {
    renderWithProviders(<EnvironmentSelector />);
    fireEvent.click(screen.getByRole('button', { name: /environment/i }));
    fireEvent.click(screen.getByText('Staging'));
    expect(mockSwitchEnvironment).toHaveBeenCalledWith('staging');
  });

  it('does not call switchEnvironment when selecting the active env', () => {
    renderWithProviders(<EnvironmentSelector />);
    fireEvent.click(screen.getByRole('button', { name: /environment/i }));
    // Click the option (role=option) not the trigger button
    fireEvent.click(screen.getByRole('option', { name: /development/i }));
    expect(mockSwitchEnvironment).not.toHaveBeenCalled();
  });

  it('shows lock icon for read-only environment', () => {
    mockPortalEnvironment.mockReturnValue(makeEnvContext('prod'));
    renderWithProviders(<EnvironmentSelector />);
    expect(screen.getByLabelText('Read-only')).toBeInTheDocument();
  });

  it('does not render when only 1 environment', () => {
    mockPortalEnvironment.mockReturnValue({
      ...makeEnvContext(),
      environments: [{ name: 'dev', label: 'Development', mode: 'full', color: 'green' }],
    });
    const { container } = renderWithProviders(<EnvironmentSelector />);
    expect(container.firstChild).toBeNull();
  });

  it('does not render while loading', () => {
    mockPortalEnvironment.mockReturnValue({ ...makeEnvContext(), loading: true });
    const { container } = renderWithProviders(<EnvironmentSelector />);
    expect(container.firstChild).toBeNull();
  });

  it('renders mobile variant with all options visible', () => {
    renderWithProviders(<EnvironmentSelector variant="mobile" />);
    expect(screen.getByText('Environment')).toBeInTheDocument();
    expect(screen.getByText('Development')).toBeInTheDocument();
    expect(screen.getByText('Staging')).toBeInTheDocument();
    expect(screen.getByText('Production')).toBeInTheDocument();
  });
});
