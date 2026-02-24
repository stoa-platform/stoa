import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EnvironmentSelector, type Environment } from './EnvironmentSelector';
import { renderWithProviders } from '../../test/helpers';

vi.mock('../../config', () => ({
  config: {
    portalMode: 'production',
  },
}));

const environments: Environment[] = [
  {
    id: 'dev',
    name: 'dev',
    displayName: 'Development',
    baseUrl: 'https://api.dev.gostoa.dev',
    isProduction: false,
  },
  {
    id: 'staging',
    name: 'staging',
    displayName: 'Staging',
    baseUrl: 'https://api.staging.gostoa.dev',
    isProduction: false,
  },
  {
    id: 'prod',
    name: 'prod',
    displayName: 'Production EU',
    baseUrl: 'https://api.gostoa.dev',
    isProduction: true,
  },
];

describe('EnvironmentSelector', () => {
  const onSelect = vi.fn();

  const defaultProps = {
    environments,
    selectedEnvironment: environments[0],
    onSelect,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render label', () => {
    renderWithProviders(<EnvironmentSelector {...defaultProps} />);
    expect(screen.getByText('Target Environment')).toBeInTheDocument();
  });

  it('should render all environment options', () => {
    renderWithProviders(<EnvironmentSelector {...defaultProps} />);
    expect(screen.getByText('Development')).toBeInTheDocument();
    expect(screen.getByText('Staging')).toBeInTheDocument();
    expect(screen.getByText('Production EU (Production)')).toBeInTheDocument();
  });

  it('should show selected environment', () => {
    renderWithProviders(<EnvironmentSelector {...defaultProps} />);
    const select = screen.getByLabelText('Target Environment');
    expect(select).toHaveValue('dev');
  });

  it('should call onSelect when environment changes', async () => {
    const user = userEvent.setup();
    renderWithProviders(<EnvironmentSelector {...defaultProps} />);
    await user.selectOptions(screen.getByLabelText('Target Environment'), 'prod');
    expect(onSelect).toHaveBeenCalledWith(environments[2]);
  });

  it('should show base URL for selected environment', () => {
    renderWithProviders(<EnvironmentSelector {...defaultProps} />);
    expect(screen.getByText('https://api.dev.gostoa.dev')).toBeInTheDocument();
  });

  it('should show production warning when production environment selected', () => {
    renderWithProviders(
      <EnvironmentSelector {...defaultProps} selectedEnvironment={environments[2]} />
    );
    expect(screen.getByText(/You are targeting a/)).toBeInTheDocument();
    expect(screen.getByText(/production/)).toBeInTheDocument();
  });

  it('should mention audit logging on production portal', () => {
    renderWithProviders(
      <EnvironmentSelector {...defaultProps} selectedEnvironment={environments[2]} />
    );
    expect(screen.getByText(/Requests will be logged for audit purposes/)).toBeInTheDocument();
  });

  it('should not show production warning for non-production environments', () => {
    renderWithProviders(<EnvironmentSelector {...defaultProps} />);
    expect(screen.queryByText(/You are targeting a/)).not.toBeInTheDocument();
  });

  it('should show empty state when no environments', () => {
    renderWithProviders(
      <EnvironmentSelector environments={[]} selectedEnvironment={null} onSelect={onSelect} />
    );
    expect(screen.getByText('No environments available')).toBeInTheDocument();
  });

  it('should disable select when disabled prop is true', () => {
    renderWithProviders(<EnvironmentSelector {...defaultProps} disabled={true} />);
    expect(screen.getByLabelText('Target Environment')).toBeDisabled();
  });

  it('should not show base URL when no environment selected', () => {
    renderWithProviders(
      <EnvironmentSelector
        environments={environments}
        selectedEnvironment={null}
        onSelect={onSelect}
      />
    );
    expect(screen.queryByText('Base URL:')).not.toBeInTheDocument();
  });
});
