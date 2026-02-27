import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../../test/helpers';
import { MarketplaceCard } from '../MarketplaceCard';
import type { MarketplaceItem } from '../../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

vi.mock('../../../i18n', () => ({ loadNamespace: vi.fn(), LANGUAGE_KEY: 'stoa:language' }));
vi.mock('../../../config', () => ({ config: { features: { enableI18n: false } } }));

function makeItem(overrides: Partial<MarketplaceItem> = {}): MarketplaceItem {
  return {
    id: 'api-123',
    type: 'api',
    name: 'Test API',
    displayName: 'Test API Display',
    description: 'A test API description',
    category: 'payments',
    tags: ['rest', 'json'],
    status: 'published',
    version: '1.0.0',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-02T00:00:00Z',
    ...overrides,
  };
}

describe('MarketplaceCard', () => {
  it('renders display name and description', () => {
    renderWithProviders(<MarketplaceCard item={makeItem()} />);

    expect(screen.getByText('Test API Display')).toBeInTheDocument();
    expect(screen.getByText('A test API description')).toBeInTheDocument();
  });

  it('renders API type label for api items', () => {
    renderWithProviders(<MarketplaceCard item={makeItem({ type: 'api' })} />);

    expect(screen.getByText('API')).toBeInTheDocument();
  });

  it('renders AI Tool type label for mcp-server items', () => {
    renderWithProviders(<MarketplaceCard item={makeItem({ type: 'mcp-server', id: 'mcp-456' })} />);

    expect(screen.getByText('AI Tool')).toBeInTheDocument();
  });

  it('renders version when provided', () => {
    renderWithProviders(<MarketplaceCard item={makeItem({ version: '2.3.1' })} />);

    expect(screen.getByText('v2.3.1')).toBeInTheDocument();
  });

  it('renders tags up to max of 3', () => {
    renderWithProviders(
      <MarketplaceCard item={makeItem({ tags: ['tag1', 'tag2', 'tag3', 'tag4', 'tag5'] })} />
    );

    expect(screen.getByText('tag1')).toBeInTheDocument();
    expect(screen.getByText('tag2')).toBeInTheDocument();
    expect(screen.getByText('tag3')).toBeInTheDocument();
    expect(screen.getByText('+2')).toBeInTheDocument();
  });

  it('renders featured badge when item is featured', () => {
    renderWithProviders(<MarketplaceCard item={makeItem({ featured: true })} />);

    expect(screen.getByText('Featured')).toBeInTheDocument();
  });

  it('does not render featured badge when not featured', () => {
    renderWithProviders(<MarketplaceCard item={makeItem()} />);

    expect(screen.queryByText('Featured')).not.toBeInTheDocument();
  });

  it('renders a link to the correct API path', () => {
    renderWithProviders(
      <MarketplaceCard
        item={makeItem({
          id: 'api-abc',
          type: 'api',
          api: { id: 'abc' } as MarketplaceItem['api'],
        })}
      />
    );

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/apis/abc');
  });

  it('renders a link to the correct MCP server path', () => {
    renderWithProviders(
      <MarketplaceCard
        item={makeItem({
          id: 'mcp-xyz',
          type: 'mcp-server',
          mcpServer: { id: 'xyz' } as MarketplaceItem['mcpServer'],
        })}
      />
    );

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/servers/xyz');
  });

  it('renders status badge', () => {
    renderWithProviders(<MarketplaceCard item={makeItem({ status: 'published' })} />);

    expect(screen.getByText('published')).toBeInTheDocument();
  });

  it('renders with empty tags gracefully', () => {
    renderWithProviders(<MarketplaceCard item={makeItem({ tags: [] })} />);

    expect(screen.getByText('Test API Display')).toBeInTheDocument();
  });

  it('renders with empty description', () => {
    renderWithProviders(<MarketplaceCard item={makeItem({ description: '' })} />);

    expect(screen.getByText('Test API Display')).toBeInTheDocument();
  });
});
