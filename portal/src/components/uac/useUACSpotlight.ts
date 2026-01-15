/**
 * useUACSpotlight Hook
 *
 * Manages the state for the first-time user UAC education spotlight.
 * Persists dismissal in localStorage so users only see it once.
 *
 * Reference: CAB-564 - UAC Badge & Tooltips
 */

import { useState, useEffect, useCallback } from 'react';

const SPOTLIGHT_STORAGE_KEY = 'stoa_uac_spotlight_dismissed';

interface UseUACSpotlightReturn {
  /** Whether to show the spotlight banner */
  showSpotlight: boolean;
  /** Call to dismiss the spotlight (persists to localStorage) */
  dismissSpotlight: () => void;
  /** Reset spotlight state (for testing/debug) */
  resetSpotlight: () => void;
}

/**
 * Hook to manage UAC spotlight visibility for first-time users.
 *
 * @example
 * ```tsx
 * const { showSpotlight, dismissSpotlight } = useUACSpotlight();
 *
 * return showSpotlight && (
 *   <UACSpotlight onDismiss={dismissSpotlight} />
 * );
 * ```
 */
export function useUACSpotlight(): UseUACSpotlightReturn {
  const [showSpotlight, setShowSpotlight] = useState(false);

  useEffect(() => {
    // Check if user has already seen the spotlight
    const dismissed = localStorage.getItem(SPOTLIGHT_STORAGE_KEY);
    if (!dismissed) {
      // Delay to let the page load first
      const timer = setTimeout(() => {
        setShowSpotlight(true);
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, []);

  const dismissSpotlight = useCallback(() => {
    setShowSpotlight(false);
    localStorage.setItem(SPOTLIGHT_STORAGE_KEY, 'true');
  }, []);

  const resetSpotlight = useCallback(() => {
    localStorage.removeItem(SPOTLIGHT_STORAGE_KEY);
    setShowSpotlight(true);
  }, []);

  return {
    showSpotlight,
    dismissSpotlight,
    resetSpotlight,
  };
}

export default useUACSpotlight;
