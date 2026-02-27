import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithProviders } from '../../../test/helpers';
import { MarketplaceSearch } from '../MarketplaceSearch';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

vi.mock('../../../i18n', () => ({ loadNamespace: vi.fn(), LANGUAGE_KEY: 'stoa:language' }));
vi.mock('../../../config', () => ({ config: { features: { enableI18n: false } } }));

describe('MarketplaceSearch', () => {
  const onChange = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the search input', () => {
    renderWithProviders(<MarketplaceSearch value="" onChange={onChange} />);

    const input = screen.getByRole('textbox');
    expect(input).toBeInTheDocument();
  });

  it('renders default placeholder', () => {
    renderWithProviders(<MarketplaceSearch value="" onChange={onChange} />);

    expect(screen.getByPlaceholderText('Search APIs, AI tools, and more...')).toBeInTheDocument();
  });

  it('renders custom placeholder', () => {
    renderWithProviders(
      <MarketplaceSearch value="" onChange={onChange} placeholder="Custom search" />
    );

    expect(screen.getByPlaceholderText('Custom search')).toBeInTheDocument();
  });

  it('displays the current value', () => {
    renderWithProviders(<MarketplaceSearch value="test query" onChange={onChange} />);

    const input = screen.getByRole('textbox') as HTMLInputElement;
    expect(input.value).toBe('test query');
  });

  it('calls onChange when user types', () => {
    renderWithProviders(<MarketplaceSearch value="" onChange={onChange} />);

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'payment' } });
    expect(onChange).toHaveBeenCalledWith('payment');
  });

  it('renders the search icon', () => {
    const { container } = renderWithProviders(<MarketplaceSearch value="" onChange={onChange} />);

    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
  });
});
