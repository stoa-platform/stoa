import { useEffect, useCallback, useRef } from 'react';

// ============================================================================
// Types
// ============================================================================

export interface KeyboardShortcut {
  /** Key to listen for (e.g., 'k', 'Enter', 'Escape') */
  key: string;
  /** Require Cmd/Ctrl modifier */
  meta?: boolean;
  /** Require Shift modifier */
  shift?: boolean;
  /** Require Alt/Option modifier */
  alt?: boolean;
  /** Callback when shortcut is triggered */
  handler: (e: KeyboardEvent) => void;
  /** Prevent default browser behavior */
  preventDefault?: boolean;
  /** Description for help display */
  description?: string;
}

export interface UseKeyboardShortcutsOptions {
  /** Whether shortcuts are enabled */
  enabled?: boolean;
  /** Disable shortcuts when focus is in an input/textarea */
  disableInInputs?: boolean;
}

// ============================================================================
// Hook
// ============================================================================

/**
 * Register keyboard shortcuts with support for modifiers.
 *
 * @example
 * useKeyboardShortcuts([
 *   { key: 'k', meta: true, handler: () => openCommandPalette() },
 *   { key: 'Escape', handler: () => closeModal() },
 *   { key: 'n', handler: () => createNew(), description: 'Create new item' },
 * ]);
 */
export function useKeyboardShortcuts(
  shortcuts: KeyboardShortcut[],
  options: UseKeyboardShortcutsOptions = {}
) {
  const { enabled = true, disableInInputs = true } = options;
  const shortcutsRef = useRef(shortcuts);

  // Keep shortcuts ref updated
  useEffect(() => {
    shortcutsRef.current = shortcuts;
  }, [shortcuts]);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    // Check if focus is in an input
    if (disableInInputs) {
      const target = e.target as HTMLElement;
      const tagName = target.tagName.toLowerCase();
      const isInput = tagName === 'input' || tagName === 'textarea' || target.isContentEditable;

      // Allow meta shortcuts in inputs (like Cmd+K)
      if (isInput && !(e.metaKey || e.ctrlKey)) {
        return;
      }
    }

    for (const shortcut of shortcutsRef.current) {
      const metaMatch = shortcut.meta ? (e.metaKey || e.ctrlKey) : !(e.metaKey || e.ctrlKey);
      const shiftMatch = shortcut.shift ? e.shiftKey : !e.shiftKey;
      const altMatch = shortcut.alt ? e.altKey : !e.altKey;
      const keyMatch = e.key.toLowerCase() === shortcut.key.toLowerCase();

      if (keyMatch && metaMatch && shiftMatch && altMatch) {
        if (shortcut.preventDefault !== false) {
          e.preventDefault();
        }
        shortcut.handler(e);
        return;
      }
    }
  }, [disableInInputs]);

  useEffect(() => {
    if (!enabled) return;

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [enabled, handleKeyDown]);
}

// ============================================================================
// Sequence Shortcuts (for vim-like "g then a" shortcuts)
// ============================================================================

export interface SequenceShortcut {
  /** Keys in sequence (e.g., ['g', 'a'] for "g then a") */
  keys: string[];
  /** Handler when sequence is completed */
  handler: () => void;
  /** Description for help display */
  description?: string;
}

/**
 * Register sequence shortcuts (like vim's "g then a").
 *
 * @example
 * useSequenceShortcuts([
 *   { keys: ['g', 'a'], handler: () => navigate('/apis'), description: 'Go to APIs' },
 *   { keys: ['g', 'd'], handler: () => navigate('/dashboard'), description: 'Go to Dashboard' },
 * ]);
 */
export function useSequenceShortcuts(
  sequences: SequenceShortcut[],
  options: UseKeyboardShortcutsOptions = {}
) {
  const { enabled = true, disableInInputs = true } = options;
  const sequenceRef = useRef<string[]>([]);
  const timeoutRef = useRef<number>(undefined);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    // Ignore modifier keys
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    // Check if focus is in an input
    if (disableInInputs) {
      const target = e.target as HTMLElement;
      const tagName = target.tagName.toLowerCase();
      if (tagName === 'input' || tagName === 'textarea' || target.isContentEditable) {
        return;
      }
    }

    // Clear timeout and add key to sequence
    if (timeoutRef.current) {
      window.clearTimeout(timeoutRef.current);
    }
    sequenceRef.current.push(e.key.toLowerCase());

    // Check for matching sequence
    for (const sequence of sequences) {
      const currentKeys = sequenceRef.current.slice(-sequence.keys.length);
      if (
        currentKeys.length === sequence.keys.length &&
        currentKeys.every((k, i) => k === sequence.keys[i].toLowerCase())
      ) {
        e.preventDefault();
        sequence.handler();
        sequenceRef.current = [];
        return;
      }
    }

    // Reset sequence after timeout
    timeoutRef.current = window.setTimeout(() => {
      sequenceRef.current = [];
    }, 1000);
  }, [sequences, disableInInputs]);

  useEffect(() => {
    if (!enabled) return;

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
      }
    };
  }, [enabled, handleKeyDown]);
}

// ============================================================================
// Utilities
// ============================================================================

/**
 * Format a shortcut for display (e.g., "⌘K" or "Ctrl+K")
 */
export function formatShortcut(shortcut: KeyboardShortcut): string[] {
  const parts: string[] = [];
  const isMac = typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform);

  if (shortcut.meta) {
    parts.push(isMac ? '⌘' : 'Ctrl');
  }
  if (shortcut.shift) {
    parts.push(isMac ? '⇧' : 'Shift');
  }
  if (shortcut.alt) {
    parts.push(isMac ? '⌥' : 'Alt');
  }
  parts.push(shortcut.key.toUpperCase());

  return parts;
}

export default useKeyboardShortcuts;
