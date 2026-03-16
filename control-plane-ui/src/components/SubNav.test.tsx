/**
 * SubNav component tests (CAB-1785)
 */

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import { SubNav } from './SubNav';
import {
  apiCatalogTabs,
  consumersTabs,
  applicationsTabs,
  gatewayTabs,
  observabilityTabs,
} from './subNavGroups';

function renderSubNav(tabs: typeof apiCatalogTabs, initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <SubNav tabs={tabs} />
    </MemoryRouter>
  );
}

describe('SubNav', () => {
  it('renders all tabs with labels', () => {
    renderSubNav(apiCatalogTabs);
    expect(screen.getByText('APIs')).toBeInTheDocument();
    expect(screen.getByText('Subscriptions')).toBeInTheDocument();
    expect(screen.getByText('Contracts')).toBeInTheDocument();
  });

  it('renders tabs as links with correct hrefs', () => {
    renderSubNav(apiCatalogTabs);
    const apisLink = screen.getByText('APIs').closest('a');
    expect(apisLink).toHaveAttribute('href', '/apis');
    const subscriptionsLink = screen.getByText('Subscriptions').closest('a');
    expect(subscriptionsLink).toHaveAttribute('href', '/subscriptions');
  });

  it('marks the active tab based on current path', () => {
    renderSubNav(apiCatalogTabs, '/subscriptions');
    const activeLink = screen.getByText('Subscriptions').closest('a');
    expect(activeLink).toHaveAttribute('aria-current', 'page');
    // Other tabs should not have aria-current
    const apisLink = screen.getByText('APIs').closest('a');
    expect(apisLink).not.toHaveAttribute('aria-current');
  });

  it('applies active styles to current tab', () => {
    renderSubNav(apiCatalogTabs, '/apis');
    const activeLink = screen.getByText('APIs').closest('a');
    expect(activeLink?.className).toContain('border-primary-600');
    const inactiveLink = screen.getByText('Contracts').closest('a');
    expect(inactiveLink?.className).toContain('border-transparent');
  });

  it('renders the nav element with accessible label', () => {
    renderSubNav(apiCatalogTabs);
    const nav = screen.getByRole('navigation', { name: 'Sub-navigation' });
    expect(nav).toBeInTheDocument();
  });

  describe('tab group definitions', () => {
    it('apiCatalogTabs has 3 tabs', () => {
      expect(apiCatalogTabs).toHaveLength(3);
      expect(apiCatalogTabs.map((t) => t.href)).toEqual(['/apis', '/subscriptions', '/contracts']);
    });

    it('consumersTabs has 3 tabs', () => {
      expect(consumersTabs).toHaveLength(3);
      expect(consumersTabs.map((t) => t.href)).toEqual([
        '/consumers',
        '/certificates',
        '/credential-mappings',
      ]);
    });

    it('applicationsTabs has 3 tabs', () => {
      expect(applicationsTabs).toHaveLength(3);
      expect(applicationsTabs.map((t) => t.href)).toEqual([
        '/applications',
        '/webhooks',
        '/security-posture',
      ]);
    });

    it('gatewayTabs has 4 tabs', () => {
      expect(gatewayTabs).toHaveLength(4);
      expect(gatewayTabs.map((t) => t.href)).toEqual([
        '/gateway',
        '/gateways',
        '/drift',
        '/gateway-deployments',
      ]);
    });

    it('observabilityTabs has 5 tabs', () => {
      expect(observabilityTabs).toHaveLength(5);
      expect(observabilityTabs.map((t) => t.href)).toEqual([
        '/observability',
        '/monitoring',
        '/call-flow',
        '/api-traffic',
        '/logs',
      ]);
    });
  });

  describe('bidirectional navigation', () => {
    it('shows same tabs on parent and sibling pages', () => {
      // When on /subscriptions (sibling), should show same tabs as /apis (parent)
      renderSubNav(apiCatalogTabs, '/subscriptions');
      expect(screen.getByText('APIs')).toBeInTheDocument();
      expect(screen.getByText('Subscriptions')).toBeInTheDocument();
      expect(screen.getByText('Contracts')).toBeInTheDocument();
    });

    it('handles trailing slash in path', () => {
      renderSubNav(apiCatalogTabs, '/apis/');
      const activeLink = screen.getByText('APIs').closest('a');
      expect(activeLink).toHaveAttribute('aria-current', 'page');
    });
  });

  describe('no active tab when path does not match', () => {
    it('renders all tabs without active state on unrelated path', () => {
      renderSubNav(apiCatalogTabs, '/tenants');
      const links = screen.getAllByRole('link');
      links.forEach((link) => {
        expect(link).not.toHaveAttribute('aria-current');
      });
    });
  });
});
