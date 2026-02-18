import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { EnvironmentSelector } from '../EnvironmentSelector';
import { renderWithProviders } from '../../../test/helpers';
import type { Environment } from '../EnvironmentSelector';

// Mock config
vi.mock('../../../config', () => ({
  config: {
    portalMode: 'non-production',
  },
}));

const stagingEnv: Environment = {
  id: 'staging',
  name: 'staging',
  displayName: 'Staging',
  baseUrl: 'https://api.staging.example.com',
  isProduction: false,
};

const productionEnv: Environment = {
  id: 'prod',
  name: 'production',
  displayName: 'Production',
  baseUrl: 'https://api.example.com',
  isProduction: true,
};

describe('EnvironmentSelector', () => {
  const onSelect = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders label and select', () => {
      renderWithProviders(
        <EnvironmentSelector
          environments={[stagingEnv]}
          selectedEnvironment={stagingEnv}
          onSelect={onSelect}
        />
      );
      expect(screen.getByText('Target Environment')).toBeInTheDocument();
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    it('renders all environment options', () => {
      renderWithProviders(
        <EnvironmentSelector
          environments={[stagingEnv, productionEnv]}
          selectedEnvironment={stagingEnv}
          onSelect={onSelect}
        />
      );
      expect(screen.getByRole('option', { name: 'Staging' })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: 'Production (Production)' })).toBeInTheDocument();
    });

    it('renders base URL of selected environment', () => {
      renderWithProviders(
        <EnvironmentSelector
          environments={[stagingEnv]}
          selectedEnvironment={stagingEnv}
          onSelect={onSelect}
        />
      );
      expect(screen.getByText('https://api.staging.example.com')).toBeInTheDocument();
    });

    it('renders "No environments available" when list is empty', () => {
      renderWithProviders(
        <EnvironmentSelector environments={[]} selectedEnvironment={null} onSelect={onSelect} />
      );
      expect(screen.getByText('No environments available')).toBeInTheDocument();
    });

    it('disables select when environments list is empty', () => {
      renderWithProviders(
        <EnvironmentSelector environments={[]} selectedEnvironment={null} onSelect={onSelect} />
      );
      expect(screen.getByRole('combobox')).toBeDisabled();
    });

    it('disables select when disabled=true', () => {
      renderWithProviders(
        <EnvironmentSelector
          environments={[stagingEnv]}
          selectedEnvironment={stagingEnv}
          onSelect={onSelect}
          disabled={true}
        />
      );
      expect(screen.getByRole('combobox')).toBeDisabled();
    });
  });

  describe('production warning', () => {
    it('shows production warning when production env is selected', () => {
      renderWithProviders(
        <EnvironmentSelector
          environments={[productionEnv]}
          selectedEnvironment={productionEnv}
          onSelect={onSelect}
        />
      );
      // Warning text spans multiple elements ("You are targeting a <strong>production</strong> environment")
      // Use getAllByText to find the paragraph containing the warning
      expect(screen.getByText(/You are targeting a/)).toBeInTheDocument();
    });

    it('does not show production warning for non-production env', () => {
      renderWithProviders(
        <EnvironmentSelector
          environments={[stagingEnv]}
          selectedEnvironment={stagingEnv}
          onSelect={onSelect}
        />
      );
      expect(screen.queryByText(/production environment/)).not.toBeInTheDocument();
    });
  });

  describe('selection', () => {
    it('calls onSelect with the selected environment', () => {
      renderWithProviders(
        <EnvironmentSelector
          environments={[stagingEnv, productionEnv]}
          selectedEnvironment={stagingEnv}
          onSelect={onSelect}
        />
      );
      fireEvent.change(screen.getByRole('combobox'), { target: { value: 'prod' } });
      expect(onSelect).toHaveBeenCalledWith(productionEnv);
    });

    it('does not call onSelect when an unknown id is selected', () => {
      renderWithProviders(
        <EnvironmentSelector
          environments={[stagingEnv]}
          selectedEnvironment={stagingEnv}
          onSelect={onSelect}
        />
      );
      fireEvent.change(screen.getByRole('combobox'), { target: { value: 'unknown' } });
      expect(onSelect).not.toHaveBeenCalled();
    });
  });
});
