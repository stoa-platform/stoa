import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { StepIndicator } from '../StepIndicator';
import { renderWithProviders } from '../../../test/helpers';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

describe('StepIndicator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nav with onboarding progress label', () => {
    renderWithProviders(<StepIndicator currentStep={0} />);

    expect(screen.getByRole('navigation', { name: 'Onboarding progress' })).toBeInTheDocument();
  });

  it('renders 4 step numbers when currentStep is 0', () => {
    renderWithProviders(<StepIndicator currentStep={0} />);

    // Steps 2, 3, 4 show their numbers; step 1 is current
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
  });

  it('renders step label keys via i18n', () => {
    renderWithProviders(<StepIndicator currentStep={0} />);

    expect(screen.getByText('steps.useCase')).toBeInTheDocument();
    expect(screen.getByText('steps.createApp')).toBeInTheDocument();
    expect(screen.getByText('steps.subscribe')).toBeInTheDocument();
    expect(screen.getByText('steps.firstCall')).toBeInTheDocument();
  });

  it('renders step description keys via i18n', () => {
    renderWithProviders(<StepIndicator currentStep={0} />);

    expect(screen.getByText('steps.useCaseDesc')).toBeInTheDocument();
    expect(screen.getByText('steps.createAppDesc')).toBeInTheDocument();
    expect(screen.getByText('steps.subscribeDesc')).toBeInTheDocument();
    expect(screen.getByText('steps.firstCallDesc')).toBeInTheDocument();
  });

  it('renders check icon for completed steps (currentStep=2)', () => {
    renderWithProviders(<StepIndicator currentStep={2} />);

    // Steps 0 and 1 are completed — their number is replaced by a check icon
    // Steps 3 and 4 still show numbers
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();

    // Steps 1 and 2 numbers should NOT appear (replaced by check)
    expect(screen.queryByText('1')).not.toBeInTheDocument();
    expect(screen.queryByText('2')).not.toBeInTheDocument();
  });

  it('renders all 4 steps as a list', () => {
    renderWithProviders(<StepIndicator currentStep={1} />);

    const listItems = screen.getAllByRole('listitem');
    expect(listItems).toHaveLength(4);
  });

  it('renders at step 3 showing only step 4 number', () => {
    renderWithProviders(<StepIndicator currentStep={3} />);

    // Steps 0, 1, 2 completed (check icons), step 3 is current
    expect(screen.queryByText('1')).not.toBeInTheDocument();
    expect(screen.queryByText('2')).not.toBeInTheDocument();
    expect(screen.queryByText('3')).not.toBeInTheDocument();
    // Step 4 (index 3) is current — shows "4"
    expect(screen.getByText('4')).toBeInTheDocument();
  });
});
