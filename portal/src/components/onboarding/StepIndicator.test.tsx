/**
 * Tests for StepIndicator (CAB-1306)
 */

import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { StepIndicator } from './StepIndicator';
import { renderWithProviders } from '../../test/helpers';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

describe('StepIndicator', () => {
  it('renders the onboarding progress nav', () => {
    renderWithProviders(<StepIndicator currentStep={0} />);
    expect(screen.getByRole('navigation', { name: /onboarding progress/i })).toBeInTheDocument();
  });

  it('renders 4 step list items', () => {
    renderWithProviders(<StepIndicator currentStep={0} />);
    expect(screen.getAllByRole('listitem')).toHaveLength(4);
  });

  it('shows all 4 step numbers when on step 0 (none completed)', () => {
    renderWithProviders(<StepIndicator currentStep={0} />);
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
  });

  it('shows translation key as step label', () => {
    renderWithProviders(<StepIndicator currentStep={0} />);
    expect(screen.getByText('steps.useCase')).toBeInTheDocument();
    expect(screen.getByText('steps.createApp')).toBeInTheDocument();
  });

  it('renders without error for step 3 (last step)', () => {
    expect(() => renderWithProviders(<StepIndicator currentStep={3} />)).not.toThrow();
  });

  it('shows step numbers for pending steps when first step is current', () => {
    // currentStep=0: step index 0 is current, steps 1-3 are pending → show numbers 2,3,4
    renderWithProviders(<StepIndicator currentStep={0} />);
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
  });

  it('renders all description translation keys', () => {
    renderWithProviders(<StepIndicator currentStep={0} />);
    expect(screen.getByText('steps.useCaseDesc')).toBeInTheDocument();
  });
});
