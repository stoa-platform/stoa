import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CertificateHealthBadge } from './CertificateHealthBadge';

function futureDate(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString();
}

function pastDate(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString();
}

describe('CertificateHealthBadge', () => {
  it('shows "Valid" for cert expiring in >90 days', () => {
    render(<CertificateHealthBadge status="active" notAfter={futureDate(120)} />);
    expect(screen.getByText('Valid')).toBeInTheDocument();
  });

  it('shows "Expiring Soon" for cert expiring in 30-90 days', () => {
    render(<CertificateHealthBadge status="active" notAfter={futureDate(60)} />);
    expect(screen.getByText('Expiring Soon')).toBeInTheDocument();
  });

  it('shows "Expiring" for cert expiring in 7-30 days', () => {
    render(<CertificateHealthBadge status="active" notAfter={futureDate(15)} />);
    expect(screen.getByText('Expiring')).toBeInTheDocument();
  });

  it('shows "Critical" for cert expiring in <7 days', () => {
    render(<CertificateHealthBadge status="active" notAfter={futureDate(3)} />);
    expect(screen.getByText('Critical')).toBeInTheDocument();
  });

  it('shows "Expired" for cert past expiry', () => {
    render(<CertificateHealthBadge status="active" notAfter={pastDate(5)} />);
    expect(screen.getByText('Expired')).toBeInTheDocument();
  });

  it('shows "Expired" when status is expired', () => {
    render(<CertificateHealthBadge status="expired" notAfter={pastDate(30)} />);
    expect(screen.getByText('Expired')).toBeInTheDocument();
  });

  it('shows "Revoked" when status is revoked', () => {
    render(<CertificateHealthBadge status="revoked" notAfter={futureDate(120)} />);
    expect(screen.getByText('Revoked')).toBeInTheDocument();
  });

  it('shows days remaining in parentheses for valid certs', () => {
    render(<CertificateHealthBadge status="active" notAfter={futureDate(60)} />);
    expect(screen.getByText(/\(\d+d\)/)).toBeInTheDocument();
  });

  it('does not show days for revoked certs', () => {
    render(<CertificateHealthBadge status="revoked" notAfter={futureDate(60)} />);
    expect(screen.queryByText(/\(\d+d\)/)).not.toBeInTheDocument();
  });

  it('shows tooltip with expiry info', () => {
    render(<CertificateHealthBadge status="active" notAfter={futureDate(30)} />);
    const badge = screen.getByText('Expiring').closest('span');
    expect(badge?.getAttribute('title')).toMatch(/expires in/i);
  });
});
