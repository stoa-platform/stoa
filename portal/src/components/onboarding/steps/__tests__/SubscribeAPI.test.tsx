import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { SubscribeAPI } from '../SubscribeAPI';
import { renderWithProviders, mockAPI } from '../../../../test/helpers';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

const mockUseAPIs = vi.fn();
vi.mock('../../../../hooks/useAPIs', () => ({
  useAPIs: (params: unknown) => mockUseAPIs(params),
}));

describe('SubscribeAPI', () => {
  const onSelected = vi.fn();
  const onBack = vi.fn();
  const onSkip = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    onSelected.mockReset();
    onBack.mockReset();
    onSkip.mockReset();
    mockUseAPIs.mockReturnValue({ data: { items: [] }, isLoading: false });
  });

  it('renders title via i18n', () => {
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);

    expect(screen.getByText('subscribeApi.title')).toBeInTheDocument();
  });

  it('renders subtitle via i18n', () => {
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);

    expect(screen.getByText('subscribeApi.subtitle')).toBeInTheDocument();
  });

  it('renders search input', () => {
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);

    expect(screen.getByPlaceholderText('subscribeApi.searchPlaceholder')).toBeInTheDocument();
  });

  it('renders empty state when no APIs', () => {
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);

    expect(screen.getByText('subscribeApi.noApis')).toBeInTheDocument();
  });

  it('renders loading spinner when loading', () => {
    mockUseAPIs.mockReturnValue({ data: undefined, isLoading: true });

    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);

    expect(document.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('renders API cards when APIs available', () => {
    const api1 = mockAPI({ id: 'api-1', name: 'Payment API' });
    const api2 = mockAPI({ id: 'api-2', name: 'Order API' });
    mockUseAPIs.mockReturnValue({ data: { items: [api1, api2] }, isLoading: false });

    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);

    expect(screen.getByText('Payment API')).toBeInTheDocument();
    expect(screen.getByText('Order API')).toBeInTheDocument();
  });

  it('renders API version badge', () => {
    const api = mockAPI({ version: '2.1.0' });
    mockUseAPIs.mockReturnValue({ data: { items: [api] }, isLoading: false });

    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);

    expect(screen.getByText('v2.1.0')).toBeInTheDocument();
  });

  it('calls onBack when Back button clicked', () => {
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);

    fireEvent.click(screen.getByText('subscribeApi.back'));
    expect(onBack).toHaveBeenCalledOnce();
  });

  it('calls onSkip when Skip button clicked', () => {
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);

    fireEvent.click(screen.getByText('subscribeApi.skip'));
    expect(onSkip).toHaveBeenCalledOnce();
  });

  it('continue button is disabled when no API selected', () => {
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);

    expect(screen.getByText('subscribeApi.continue')).toBeDisabled();
  });

  it('selects an API when card clicked', () => {
    const api = mockAPI({ id: 'api-1', name: 'Payment API' });
    mockUseAPIs.mockReturnValue({ data: { items: [api] }, isLoading: false });

    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);

    fireEvent.click(screen.getByText('Payment API'));

    expect(screen.getByText('subscribeApi.continue')).not.toBeDisabled();
  });

  it('calls onSelected when Continue clicked after selecting API', () => {
    const api = mockAPI({ id: 'api-1', name: 'Payment API' });
    mockUseAPIs.mockReturnValue({ data: { items: [api] }, isLoading: false });

    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);

    fireEvent.click(screen.getByText('Payment API'));
    fireEvent.click(screen.getByText('subscribeApi.continue'));

    expect(onSelected).toHaveBeenCalledWith(api);
  });

  it('updates search when typing in search input', () => {
    renderWithProviders(<SubscribeAPI onSelected={onSelected} onBack={onBack} onSkip={onSkip} />);

    fireEvent.change(screen.getByPlaceholderText('subscribeApi.searchPlaceholder'), {
      target: { value: 'payment' },
    });

    // Verify useAPIs was called with updated search
    expect(mockUseAPIs).toHaveBeenCalledWith(expect.objectContaining({ search: 'payment' }));
  });
});
