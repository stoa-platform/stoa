import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { mockExternalMCPServer, createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

vi.mock('../../services/externalMcpServersApi', () => ({
  externalMcpServersService: {
    testConnection: vi.fn().mockResolvedValue({ success: true, latency_ms: 100 }),
  },
}));

import { ExternalMCPServerModal } from './ExternalMCPServerModal';

describe('ExternalMCPServerModal', () => {
  const onClose = vi.fn();
  const onSubmit = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders create mode title when no server prop', () => {
    render(<ExternalMCPServerModal onClose={onClose} onSubmit={onSubmit} />);
    expect(screen.getByText(/Add External MCP Server/i)).toBeInTheDocument();
  });

  it('renders edit mode title when server prop provided', () => {
    render(
      <ExternalMCPServerModal
        server={mockExternalMCPServer()}
        onClose={onClose}
        onSubmit={onSubmit}
      />
    );
    expect(screen.getByText(/Edit External MCP Server/i)).toBeInTheDocument();
  });

  it('renders all required form fields', () => {
    render(<ExternalMCPServerModal onClose={onClose} onSubmit={onSubmit} />);
    expect(screen.getByText('Name')).toBeInTheDocument();
    expect(screen.getByText('Display Name')).toBeInTheDocument();
    expect(screen.getByText('Base URL')).toBeInTheDocument();
    expect(screen.getByText('Transport')).toBeInTheDocument();
  });

  it('renders save and cancel buttons', () => {
    render(<ExternalMCPServerModal onClose={onClose} onSubmit={onSubmit} />);
    expect(screen.getByText('Cancel')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Create Server/i })).toBeInTheDocument();
  });

  it('pre-fills form fields in edit mode', () => {
    render(
      <ExternalMCPServerModal
        server={mockExternalMCPServer()}
        onClose={onClose}
        onSubmit={onSubmit}
      />
    );
    expect(screen.getByDisplayValue('Linear')).toBeInTheDocument();
    expect(screen.getByDisplayValue('https://mcp.linear.app')).toBeInTheDocument();
  });

  it('renders transport options', () => {
    render(<ExternalMCPServerModal onClose={onClose} onSubmit={onSubmit} />);
    expect(screen.getByText(/SSE/)).toBeInTheDocument();
    expect(screen.getByText(/HTTP/)).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the modal', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        render(<ExternalMCPServerModal onClose={onClose} onSubmit={onSubmit} />);
        expect(screen.getByText(/Add External MCP Server/i)).toBeInTheDocument();
      });
    }
  );
});
