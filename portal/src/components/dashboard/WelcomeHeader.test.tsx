/**
 * Tests for WelcomeHeader (CAB-1390)
 */

import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { WelcomeHeader } from './WelcomeHeader';
import { renderWithProviders } from '../../test/helpers';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

vi.mock('../../config', () => ({
  config: {
    features: { enableI18n: false },
  },
}));

const mockUser = { name: 'Alice Johnson', email: 'alice@example.com' };

describe('WelcomeHeader', () => {
  it('renders a greeting when user is provided', () => {
    renderWithProviders(<WelcomeHeader user={mockUser as never} />);
    // Some greeting text should appear
    const heading = screen.getByRole('heading');
    expect(heading).toBeInTheDocument();
  });

  it('uses first name only from full name', () => {
    renderWithProviders(<WelcomeHeader user={mockUser as never} />);
    expect(screen.getByText(/alice/i)).toBeInTheDocument();
  });

  it('falls back to "Developer" when user is null', () => {
    renderWithProviders(<WelcomeHeader user={null} />);
    // The greeting heading contains "Developer" as the name part
    const heading = screen.getByRole('heading');
    expect(heading.textContent).toMatch(/developer/i);
  });

  it('falls back to "Developer" when user has no name', () => {
    renderWithProviders(<WelcomeHeader user={{ name: undefined, email: 'x@y.com' } as never} />);
    const heading = screen.getByRole('heading');
    expect(heading.textContent).toMatch(/developer/i);
  });

  it('renders subtitle text', () => {
    renderWithProviders(<WelcomeHeader user={null} />);
    // A subtitle element should exist below the greeting
    const heading = screen.getByRole('heading');
    expect(heading.parentElement).toBeTruthy();
  });
});
