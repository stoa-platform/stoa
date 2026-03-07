import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { PersonaRole } from '../test/helpers';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';

vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

vi.mock('./APIs', () => ({
  APIs: () => <div data-testid="apis-catalog">API Catalog Content</div>,
}));

vi.mock('./BackendApis', () => ({
  BackendApisList: () => <div data-testid="backend-apis-list">Backend APIs Content</div>,
}));

vi.mock('./InternalApis', () => ({
  InternalApisList: () => <div data-testid="internal-apis-list">Platform Backends Content</div>,
}));

import { APIsUnified } from './APIsUnified';

function renderComponent(initialEntries: string[] = ['/apis']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <APIsUnified />
    </MemoryRouter>
  );
}

describe('APIsUnified', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders page header', () => {
    renderComponent();
    expect(screen.getByRole('heading', { name: 'APIs' })).toBeInTheDocument();
    expect(
      screen.getByText('Manage API catalog, backend registrations, and platform proxy backends')
    ).toBeInTheDocument();
  });

  it('shows all 3 tabs for cpi-admin', () => {
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    renderComponent();
    expect(screen.getByRole('button', { name: /API Catalog/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Backend APIs/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Platform Backends/i })).toBeInTheDocument();
  });

  it.each<PersonaRole>(['tenant-admin', 'devops', 'viewer'])(
    'shows only catalog and backends tabs (no Platform Backends) for %s',
    (role) => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
      renderComponent();
      expect(screen.getByRole('button', { name: /API Catalog/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Backend APIs/i })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Platform Backends/i })).not.toBeInTheDocument();
    }
  );

  it('defaults to catalog tab and renders APIs component', () => {
    renderComponent();
    expect(screen.getByTestId('apis-catalog')).toBeInTheDocument();
    expect(screen.queryByTestId('backend-apis-list')).not.toBeInTheDocument();
    expect(screen.queryByTestId('internal-apis-list')).not.toBeInTheDocument();
  });

  it('switches to backends tab on click and renders BackendApisList', () => {
    renderComponent();
    fireEvent.click(screen.getByRole('button', { name: /Backend APIs/i }));
    expect(screen.getByTestId('backend-apis-list')).toBeInTheDocument();
    expect(screen.queryByTestId('apis-catalog')).not.toBeInTheDocument();
    expect(screen.queryByTestId('internal-apis-list')).not.toBeInTheDocument();
  });

  it('switches to platform tab on click and renders InternalApisList (cpi-admin only)', () => {
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    renderComponent();
    fireEvent.click(screen.getByRole('button', { name: /Platform Backends/i }));
    expect(screen.getByTestId('internal-apis-list')).toBeInTheDocument();
    expect(screen.queryByTestId('apis-catalog')).not.toBeInTheDocument();
    expect(screen.queryByTestId('backend-apis-list')).not.toBeInTheDocument();
  });

  it('activates backends tab when ?tab=backends is in URL', () => {
    renderComponent(['/apis?tab=backends']);
    expect(screen.getByTestId('backend-apis-list')).toBeInTheDocument();
    expect(screen.queryByTestId('apis-catalog')).not.toBeInTheDocument();
  });

  it('activates platform tab when ?tab=platform is in URL (cpi-admin)', () => {
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    renderComponent(['/apis?tab=platform']);
    expect(screen.getByTestId('internal-apis-list')).toBeInTheDocument();
    expect(screen.queryByTestId('apis-catalog')).not.toBeInTheDocument();
  });

  it('renders no tab content for an unknown tab param', () => {
    renderComponent(['/apis?tab=unknown']);
    expect(screen.queryByTestId('apis-catalog')).not.toBeInTheDocument();
    expect(screen.queryByTestId('backend-apis-list')).not.toBeInTheDocument();
    expect(screen.queryByTestId('internal-apis-list')).not.toBeInTheDocument();
    // Header is still visible
    expect(screen.getByRole('heading', { name: 'APIs' })).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page without crashing', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        expect(screen.getByRole('heading', { name: 'APIs' })).toBeInTheDocument();
      });
    }
  );
});
