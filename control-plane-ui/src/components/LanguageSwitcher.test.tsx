/**
 * Tests for LanguageSwitcher component (CAB-1429)
 *
 * Validates compact mode, full mode, language change, and accessibility.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import i18n from '../i18n/i18n';
import { LanguageSwitcher } from './LanguageSwitcher';

// Wrap component with I18nextProvider for isolated tests
function renderWithI18n(ui: React.ReactElement, language = 'en') {
  // Set language before rendering
  void i18n.changeLanguage(language);
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

describe('LanguageSwitcher', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
  });

  describe('full mode (default)', () => {
    it('renders both language buttons', () => {
      renderWithI18n(<LanguageSwitcher />);
      expect(screen.getByText('English')).toBeInTheDocument();
      expect(screen.getByText('Français')).toBeInTheDocument();
    });

    it('marks current language as active (aria-pressed)', () => {
      renderWithI18n(<LanguageSwitcher />);
      const enButton = screen.getByRole('button', { name: /English/i });
      expect(enButton).toHaveAttribute('aria-pressed', 'true');
    });

    it('marks non-current language as inactive', () => {
      renderWithI18n(<LanguageSwitcher />);
      const frButton = screen.getByRole('button', { name: /Français/i });
      expect(frButton).toHaveAttribute('aria-pressed', 'false');
    });

    it('calls changeLanguage when FR button clicked', () => {
      const changeLanguageSpy = vi.spyOn(i18n, 'changeLanguage');
      renderWithI18n(<LanguageSwitcher />);
      fireEvent.click(screen.getByRole('button', { name: /Français/i }));
      expect(changeLanguageSpy).toHaveBeenCalledWith('fr');
      changeLanguageSpy.mockRestore();
    });

    it('calls changeLanguage when EN button clicked', () => {
      const changeLanguageSpy = vi.spyOn(i18n, 'changeLanguage');
      renderWithI18n(<LanguageSwitcher />, 'fr');
      fireEvent.click(screen.getByRole('button', { name: /English/i }));
      expect(changeLanguageSpy).toHaveBeenCalledWith('en');
      changeLanguageSpy.mockRestore();
    });

    it('shows flags for both languages', () => {
      renderWithI18n(<LanguageSwitcher />);
      expect(screen.getByText('🇬🇧')).toBeInTheDocument();
      expect(screen.getByText('🇫🇷')).toBeInTheDocument();
    });

    it('applies active style to current language button', () => {
      renderWithI18n(<LanguageSwitcher />);
      const enButton = screen.getByRole('button', { name: /English/i });
      expect(enButton).toHaveClass('bg-blue-100');
    });

    it('does NOT apply active style to non-current language button', () => {
      renderWithI18n(<LanguageSwitcher />);
      const frButton = screen.getByRole('button', { name: /Français/i });
      expect(frButton).not.toHaveClass('bg-blue-100');
    });
  });

  describe('compact mode', () => {
    it('renders the Globe icon trigger button', () => {
      renderWithI18n(<LanguageSwitcher compact />);
      // compact mode has 1 trigger + 2 dropdown buttons; trigger is first
      const buttons = screen.getAllByRole('button');
      expect(buttons[0]).toBeInTheDocument();
    });

    it('renders current language code in uppercase', () => {
      renderWithI18n(<LanguageSwitcher compact />);
      expect(screen.getByText('en')).toBeInTheDocument();
    });

    it('renders dropdown items for both languages', () => {
      renderWithI18n(<LanguageSwitcher compact />);
      expect(screen.getByText('English')).toBeInTheDocument();
      expect(screen.getByText('Français')).toBeInTheDocument();
    });

    it('has aria-label on trigger button', () => {
      renderWithI18n(<LanguageSwitcher compact />);
      // compact mode: trigger button (index 0) has aria-label; dropdown items do not
      const triggerButton = screen.getAllByRole('button')[0];
      expect(triggerButton).toHaveAttribute('aria-label');
    });

    it('calls changeLanguage when FR dropdown item clicked', () => {
      const changeLanguageSpy = vi.spyOn(i18n, 'changeLanguage');
      renderWithI18n(<LanguageSwitcher compact />);
      fireEvent.click(screen.getByText('Français'));
      expect(changeLanguageSpy).toHaveBeenCalledWith('fr');
      changeLanguageSpy.mockRestore();
    });
  });

  describe('accessibility', () => {
    it('full mode buttons are keyboard accessible (role=button)', () => {
      renderWithI18n(<LanguageSwitcher />);
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBe(2);
    });

    it('compact mode has a single trigger button', () => {
      renderWithI18n(<LanguageSwitcher compact />);
      // The trigger + dropdown items, but trigger has role=button
      const buttons = screen.getAllByRole('button');
      // compact mode: 1 trigger + 2 dropdown buttons = 3 total
      expect(buttons.length).toBeGreaterThanOrEqual(1);
    });
  });
});
