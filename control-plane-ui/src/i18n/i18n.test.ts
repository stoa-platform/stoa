/**
 * Tests for i18n framework initialization (CAB-1429)
 *
 * Validates that i18next is correctly initialized with EN/FR locales,
 * the language detector, and all three namespaces.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import i18n from './i18n';

describe('i18n initialization', () => {
  it('initializes successfully', () => {
    expect(i18n.isInitialized).toBe(true);
  });

  it('defaults to English fallback language', () => {
    // i18next normalizes fallbackLng to an array internally
    const fallback = i18n.options.fallbackLng;
    const fallbackArr = Array.isArray(fallback) ? fallback : [fallback];
    expect(fallbackArr).toContain('en');
  });

  it('supports English and French', () => {
    const supported = i18n.options.supportedLngs;
    expect(supported).toContain('en');
    expect(supported).toContain('fr');
  });

  it('has three namespaces: common, navigation, pages', () => {
    const ns = i18n.options.ns as string[];
    expect(ns).toContain('common');
    expect(ns).toContain('navigation');
    expect(ns).toContain('pages');
  });

  it('uses common as the default namespace', () => {
    expect(i18n.options.defaultNS).toBe('common');
  });

  it('loads EN common translations', () => {
    const value = i18n.getFixedT('en', 'common')('actions.save');
    expect(value).toBe('Save');
  });

  it('loads FR common translations', () => {
    const value = i18n.getFixedT('fr', 'common')('actions.save');
    expect(value).toBe('Enregistrer');
  });

  it('loads EN pages.dashboard.title', () => {
    const value = i18n.getFixedT('en', 'pages')('dashboard.title');
    expect(value).toBe('Dashboard');
  });

  it('loads FR pages.dashboard.title', () => {
    const value = i18n.getFixedT('fr', 'pages')('dashboard.title');
    expect(value).toBe('Tableau de bord');
  });

  it('loads EN pages.login.loginButton', () => {
    const value = i18n.getFixedT('en', 'pages')('login.loginButton');
    expect(value).toBe('Login with Keycloak');
  });

  it('loads FR pages.login.loginButton', () => {
    const value = i18n.getFixedT('fr', 'pages')('login.loginButton');
    expect(value).toBe('Se connecter avec Keycloak');
  });

  it('loads EN navigation.items.dashboard', () => {
    const value = i18n.getFixedT('en', 'navigation')('items.dashboard');
    expect(value).toBe('Dashboard');
  });

  it('loads FR navigation.items.dashboard', () => {
    const value = i18n.getFixedT('fr', 'navigation')('items.dashboard');
    expect(value).toBe('Tableau de bord');
  });

  it('handles interpolation in pages.dashboard.hello', () => {
    const value = i18n.getFixedT('en', 'pages')('dashboard.hello', { name: 'Wade' });
    expect(value).toBe('Hello, Wade!');
  });

  it('handles interpolation in FR pages.dashboard.hello', () => {
    const value = i18n.getFixedT('fr', 'pages')('dashboard.hello', { name: 'Wade' });
    expect(value).toBe('Bonjour, Wade !');
  });

  describe('language switching', () => {
    beforeEach(async () => {
      await i18n.changeLanguage('en');
    });

    it('switches to French', async () => {
      await i18n.changeLanguage('fr');
      expect(i18n.language).toBe('fr');
    });

    it('switches back to English', async () => {
      await i18n.changeLanguage('fr');
      await i18n.changeLanguage('en');
      expect(i18n.language).toBe('en');
    });

    it('translates correctly after language switch to FR', async () => {
      await i18n.changeLanguage('fr');
      expect(i18n.t('actions.save', { ns: 'common' })).toBe('Enregistrer');
    });

    it('translates correctly after language switch back to EN', async () => {
      await i18n.changeLanguage('fr');
      await i18n.changeLanguage('en');
      expect(i18n.t('actions.save', { ns: 'common' })).toBe('Save');
    });
  });
});
