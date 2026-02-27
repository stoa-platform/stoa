import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../../test/helpers';
import { MarketplaceStatsBar } from '../MarketplaceStats';
import type { MarketplaceStats } from '../../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

vi.mock('../../../i18n', () => ({ loadNamespace: vi.fn(), LANGUAGE_KEY: 'stoa:language' }));
vi.mock('../../../config', () => ({ config: { features: { enableI18n: false } } }));

describe('MarketplaceStatsBar', () => {
  const defaultStats: MarketplaceStats = {
    totalAPIs: 12,
    totalMCPServers: 5,
    totalItems: 17,
    categories: [],
  };

  it('renders total APIs count', () => {
    renderWithProviders(<MarketplaceStatsBar stats={defaultStats} />);

    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('renders total MCP servers count', () => {
    renderWithProviders(<MarketplaceStatsBar stats={defaultStats} />);

    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('renders total items count', () => {
    renderWithProviders(<MarketplaceStatsBar stats={defaultStats} />);

    expect(screen.getByText('17')).toBeInTheDocument();
  });

  it('renders labels for each stat', () => {
    renderWithProviders(<MarketplaceStatsBar stats={defaultStats} />);

    expect(screen.getByText(/APIs/)).toBeInTheDocument();
    expect(screen.getByText(/AI Tools/)).toBeInTheDocument();
    expect(screen.getByText(/Total/)).toBeInTheDocument();
  });

  it('renders with zero stats', () => {
    renderWithProviders(
      <MarketplaceStatsBar
        stats={{ totalAPIs: 0, totalMCPServers: 0, totalItems: 0, categories: [] }}
      />
    );

    const zeros = screen.getAllByText('0');
    expect(zeros.length).toBeGreaterThanOrEqual(3);
  });
});
