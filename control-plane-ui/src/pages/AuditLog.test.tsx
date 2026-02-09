import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AuditLog } from './AuditLog';

describe('AuditLog', () => {
  it('renders title and coming soon card', () => {
    render(<AuditLog />);
    expect(screen.getByText('Audit Log')).toBeInTheDocument();
    expect(screen.getByText('Coming Soon')).toBeInTheDocument();
  });
});
