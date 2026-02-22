/**
 * Tests for SubscribeAPI step (CAB-1306)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { SubscribeAPI } from './SubscribeAPI';
import { renderWithProviders, mockAPI } from '../../../test/helpers';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const mockUseAPIs = vi.fn();

vi.mock('../../../hooks/useAPIs', () => ({
  useAPIs: (...args: unknown[]) => mockUseAPIs(...args),
}));

describe('SubscribeAPI', () => {
  const onSelected = vi.fn();
  const onBack = vi.fn();
  const onSkip = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAPIs.mockReturnValue({ data: undefined, isLoading: false });
  });

  it('renders the step title', () => {
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);
    expect(screen.getByText('subscribeApi.title')).toBeInTheDocument();
  });

  it('shows loading spinner while APIs are loading', () => {
    mockUseAPIs.mockReturnValue({ data: undefined, isLoading: true });
    const { container } = renderWithProviders(
      <SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />
    );
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('shows empty state text when no APIs are available', () => {
    mockUseAPIs.mockReturnValue({ data: { items: [] }, isLoading: false });
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);
    expect(screen.getByText('subscribeApi.noApis')).toBeInTheDocument();
  });

  it('renders API cards when APIs are available', () => {
    mockUseAPIs.mockReturnValue({
      data: { items: [mockAPI(), mockAPI({ id: 'api-2', name: 'Orders API' })] },
      isLoading: false,
    });
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);
    expect(screen.getByText('Payment API')).toBeInTheDocument();
    expect(screen.getByText('Orders API')).toBeInTheDocument();
  });

  it('Continue button is disabled when no API is selected', () => {
    mockUseAPIs.mockReturnValue({
      data: { items: [mockAPI()] },
      isLoading: false,
    });
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);
    expect(screen.getByRole('button', { name: 'subscribeApi.continue' })).toBeDisabled();
  });

  it('Continue button is enabled after selecting an API', () => {
    mockUseAPIs.mockReturnValue({
      data: { items: [mockAPI()] },
      isLoading: false,
    });
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);
    fireEvent.click(screen.getByText('Payment API'));
    expect(screen.getByRole('button', { name: 'subscribeApi.continue' })).not.toBeDisabled();
  });

  it('clicking Continue with a selected API calls onSelected', () => {
    const api = mockAPI();
    mockUseAPIs.mockReturnValue({
      data: { items: [api] },
      isLoading: false,
    });
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);
    fireEvent.click(screen.getByText('Payment API'));
    fireEvent.click(screen.getByRole('button', { name: 'subscribeApi.continue' }));
    expect(onSelected).toHaveBeenCalledWith(expect.objectContaining({ id: 'api-1' }));
  });

  it('clicking Skip calls onSkip', () => {
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);
    fireEvent.click(screen.getByRole('button', { name: 'subscribeApi.skip' }));
    expect(onSkip).toHaveBeenCalled();
  });

  it('clicking Back calls onBack', () => {
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);
    fireEvent.click(screen.getByRole('button', { name: 'subscribeApi.back' }));
    expect(onBack).toHaveBeenCalled();
  });
});
