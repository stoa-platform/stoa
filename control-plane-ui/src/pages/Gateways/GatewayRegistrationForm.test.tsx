import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

vi.mock('../../services/api', () => ({
  apiService: {
    createGatewayInstance: vi.fn().mockResolvedValue({}),
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
  },
}));

import { GatewayRegistrationForm } from './GatewayRegistrationForm';

describe('GatewayRegistrationForm', () => {
  const onCreated = vi.fn();
  const onCancel = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the heading', () => {
    render(<GatewayRegistrationForm onCreated={onCreated} onCancel={onCancel} />);
    expect(screen.getByRole('heading', { name: /Register Gateway/i })).toBeInTheDocument();
  });

  it('renders all required form fields', () => {
    render(<GatewayRegistrationForm onCreated={onCreated} onCancel={onCancel} />);
    expect(screen.getByText('Name')).toBeInTheDocument();
    expect(screen.getByText('Display Name')).toBeInTheDocument();
    expect(screen.getByText('Gateway Type')).toBeInTheDocument();
    expect(screen.getByText('Environment')).toBeInTheDocument();
    expect(screen.getByText(/Admin API URL/)).toBeInTheDocument();
  });

  it('renders gateway type options', () => {
    render(<GatewayRegistrationForm onCreated={onCreated} onCancel={onCancel} />);
    expect(screen.getByText('webMethods')).toBeInTheDocument();
    expect(screen.getByText('STOA')).toBeInTheDocument();
  });

  it('renders environment options', () => {
    render(<GatewayRegistrationForm onCreated={onCreated} onCancel={onCancel} />);
    expect(screen.getByText('dev')).toBeInTheDocument();
    expect(screen.getByText('staging')).toBeInTheDocument();
    expect(screen.getByText('production')).toBeInTheDocument();
  });

  it('renders register and cancel buttons', () => {
    render(<GatewayRegistrationForm onCreated={onCreated} onCancel={onCancel} />);
    expect(screen.getByRole('button', { name: /Register Gateway/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the form', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        render(<GatewayRegistrationForm onCreated={onCreated} onCancel={onCancel} />);
        expect(screen.getByRole('heading', { name: /Register Gateway/i })).toBeInTheDocument();
      });
    }
  );
});
