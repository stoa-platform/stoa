import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LanguageToggle } from './LanguageToggle';

// Mock react-i18next
const mockChangeLanguage = vi.fn();
let mockLanguage = 'en';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      get language() {
        return mockLanguage;
      },
      changeLanguage: mockChangeLanguage,
    },
  }),
}));

// Mock i18n module
vi.mock('../../i18n', () => ({
  LANGUAGE_KEY: 'stoa:language',
  loadNamespace: vi.fn(),
}));

describe('LanguageToggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLanguage = 'en';
    localStorage.clear();
  });

  it('should render with current language label', () => {
    render(<LanguageToggle />);

    expect(screen.getByText('EN')).toBeInTheDocument();
    expect(screen.getByLabelText('Switch language (current: EN)')).toBeInTheDocument();
  });

  it('should show FR when language is French', () => {
    mockLanguage = 'fr';
    render(<LanguageToggle />);

    expect(screen.getByText('FR')).toBeInTheDocument();
  });

  it('should toggle to French when clicking from English', async () => {
    const user = userEvent.setup();
    render(<LanguageToggle />);

    await user.click(screen.getByLabelText('Switch language (current: EN)'));

    expect(mockChangeLanguage).toHaveBeenCalledWith('fr');
    expect(localStorage.getItem('stoa:language')).toBe('fr');
  });

  it('should toggle to English when clicking from French', async () => {
    mockLanguage = 'fr';
    const user = userEvent.setup();
    render(<LanguageToggle />);

    await user.click(screen.getByLabelText('Switch language (current: FR)'));

    expect(mockChangeLanguage).toHaveBeenCalledWith('en');
    expect(localStorage.getItem('stoa:language')).toBe('en');
  });

  it('should have a globe icon', () => {
    render(<LanguageToggle />);

    const button = screen.getByRole('button');
    expect(button).toBeInTheDocument();
  });
});
