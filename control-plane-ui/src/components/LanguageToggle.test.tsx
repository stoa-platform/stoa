import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LanguageToggle } from './LanguageToggle';

const mockChangeLanguage = vi.fn();

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en', changeLanguage: mockChangeLanguage },
    t: (key: string) => key,
  }),
}));

vi.mock('../i18n', () => ({
  LANGUAGE_KEY: 'stoa-lang',
  loadNamespace: vi.fn(),
}));

describe('LanguageToggle', () => {
  it('renders current language label', () => {
    render(<LanguageToggle />);
    expect(screen.getByText('EN')).toBeInTheDocument();
  });

  it('has accessible label', () => {
    render(<LanguageToggle />);
    expect(screen.getByLabelText('Switch language (current: EN)')).toBeInTheDocument();
  });

  it('calls changeLanguage on click', () => {
    render(<LanguageToggle />);
    fireEvent.click(screen.getByRole('button'));
    expect(mockChangeLanguage).toHaveBeenCalledWith('fr');
  });
});
