import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithProviders } from '../../../test/helpers';
import { MarketplaceFilterBar } from '../MarketplaceFilters';
import type { MarketplaceCategory } from '../../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

vi.mock('../../../i18n', () => ({ loadNamespace: vi.fn(), LANGUAGE_KEY: 'stoa:language' }));
vi.mock('../../../config', () => ({ config: { features: { enableI18n: false } } }));

const mockCategories: MarketplaceCategory[] = [
  { id: 'payments', name: 'payments', count: 5 },
  { id: 'ai', name: 'ai', count: 3 },
  { id: 'data', name: 'data', count: 2 },
];

describe('MarketplaceFilterBar', () => {
  const onTypeChange = vi.fn();
  const onCategoryChange = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders type filter buttons', () => {
    renderWithProviders(
      <MarketplaceFilterBar
        selectedType="all"
        onTypeChange={onTypeChange}
        categories={mockCategories}
        selectedCategory=""
        onCategoryChange={onCategoryChange}
      />
    );

    expect(screen.getByText('All')).toBeInTheDocument();
    expect(screen.getByText('APIs')).toBeInTheDocument();
    expect(screen.getByText('AI Tools')).toBeInTheDocument();
  });

  it('calls onTypeChange when a type button is clicked', () => {
    renderWithProviders(
      <MarketplaceFilterBar
        selectedType="all"
        onTypeChange={onTypeChange}
        categories={mockCategories}
        selectedCategory=""
        onCategoryChange={onCategoryChange}
      />
    );

    fireEvent.click(screen.getByText('APIs'));
    expect(onTypeChange).toHaveBeenCalledWith('api');
  });

  it('calls onTypeChange with mcp-server for AI Tools click', () => {
    renderWithProviders(
      <MarketplaceFilterBar
        selectedType="all"
        onTypeChange={onTypeChange}
        categories={mockCategories}
        selectedCategory=""
        onCategoryChange={onCategoryChange}
      />
    );

    fireEvent.click(screen.getByText('AI Tools'));
    expect(onTypeChange).toHaveBeenCalledWith('mcp-server');
  });

  it('highlights the selected type', () => {
    renderWithProviders(
      <MarketplaceFilterBar
        selectedType="api"
        onTypeChange={onTypeChange}
        categories={mockCategories}
        selectedCategory=""
        onCategoryChange={onCategoryChange}
      />
    );

    const apisButton = screen.getByText('APIs').closest('button');
    expect(apisButton).toHaveClass('bg-white');
    expect(apisButton).toHaveClass('text-emerald-700');
  });

  it('renders category select with options', () => {
    renderWithProviders(
      <MarketplaceFilterBar
        selectedType="all"
        onTypeChange={onTypeChange}
        categories={mockCategories}
        selectedCategory=""
        onCategoryChange={onCategoryChange}
      />
    );

    const select = screen.getByRole('combobox');
    expect(select).toBeInTheDocument();
    expect(screen.getByText('payments (5)')).toBeInTheDocument();
  });

  it('calls onCategoryChange when category is selected', () => {
    renderWithProviders(
      <MarketplaceFilterBar
        selectedType="all"
        onTypeChange={onTypeChange}
        categories={mockCategories}
        selectedCategory=""
        onCategoryChange={onCategoryChange}
      />
    );

    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'payments' } });
    expect(onCategoryChange).toHaveBeenCalledWith('payments');
  });

  it('renders with empty categories', () => {
    renderWithProviders(
      <MarketplaceFilterBar
        selectedType="all"
        onTypeChange={onTypeChange}
        categories={[]}
        selectedCategory=""
        onCategoryChange={onCategoryChange}
      />
    );

    expect(screen.getByText('All')).toBeInTheDocument();
  });
});
