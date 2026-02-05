import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: string;
  type: ToastType;
  title: string;
  description?: string;
  duration?: number; // ms, 0 = persist
  action?: {
    label: string;
    onClick: () => void;
  };
}

interface ToastContextValue {
  toasts: Toast[];
  addToast: (toast: Omit<Toast, 'id'>) => string;
  removeToast: (id: string) => void;
  clearAll: () => void;
}

// ============================================================================
// Context
// ============================================================================

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}

// Convenience methods
export function useToastActions() {
  const { addToast, removeToast, clearAll } = useToast();

  return {
    success: (title: string, description?: string, duration = 4000) =>
      addToast({ type: 'success', title, description, duration }),
    error: (title: string, description?: string, duration = 0) =>
      addToast({ type: 'error', title, description, duration }),
    warning: (title: string, description?: string, duration = 5000) =>
      addToast({ type: 'warning', title, description, duration }),
    info: (title: string, description?: string, duration = 4000) =>
      addToast({ type: 'info', title, description, duration }),
    dismiss: removeToast,
    clearAll,
  };
}

// ============================================================================
// Provider
// ============================================================================

const MAX_TOASTS = 3;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const newToast: Toast = { ...toast, id };

    setToasts((prev) => {
      // Keep only the most recent MAX_TOASTS - 1 to make room for new one
      const limited = prev.slice(-(MAX_TOASTS - 1));
      return [...limited, newToast];
    });

    return id;
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const clearAll = useCallback(() => {
    setToasts([]);
  }, []);

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast, clearAll }}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={removeToast} />
    </ToastContext.Provider>
  );
}

// ============================================================================
// Toast Container
// ============================================================================

interface ToastContainerProps {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}

function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  return (
    <div
      aria-live="polite"
      aria-label="Notifications"
      className="fixed top-4 right-4 z-[100] flex flex-col gap-3 w-full max-w-sm pointer-events-none"
    >
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

// ============================================================================
// Toast Item
// ============================================================================

interface ToastItemProps {
  toast: Toast;
  onDismiss: (id: string) => void;
}

const ICONS: Record<ToastType, React.ComponentType<{ className?: string }>> = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

const STYLES: Record<ToastType, { bg: string; icon: string; border: string }> = {
  success: {
    bg: 'bg-white dark:bg-neutral-800',
    icon: 'text-success-500',
    border: 'border-success-200 dark:border-success-700',
  },
  error: {
    bg: 'bg-white dark:bg-neutral-800',
    icon: 'text-error-500',
    border: 'border-error-200 dark:border-error-700',
  },
  warning: {
    bg: 'bg-white dark:bg-neutral-800',
    icon: 'text-warning-500',
    border: 'border-warning-200 dark:border-warning-700',
  },
  info: {
    bg: 'bg-white dark:bg-neutral-800',
    icon: 'text-primary-500',
    border: 'border-primary-200 dark:border-primary-700',
  },
};

function ToastItem({ toast, onDismiss }: ToastItemProps) {
  const [isExiting, setIsExiting] = useState(false);
  const Icon = ICONS[toast.type];
  const styles = STYLES[toast.type];

  // Auto-dismiss timer
  useEffect(() => {
    if (toast.duration && toast.duration > 0) {
      const timer = setTimeout(() => {
        handleDismiss();
      }, toast.duration);
      return () => clearTimeout(timer);
    }
  }, [toast.duration, toast.id]);

  const handleDismiss = () => {
    setIsExiting(true);
    setTimeout(() => {
      onDismiss(toast.id);
    }, 200); // Match animation duration
  };

  return (
    <div
      role="alert"
      className={`
        pointer-events-auto
        ${styles.bg} ${styles.border}
        border rounded-toast shadow-toast
        p-4 pr-10
        animate-slide-in-right
        ${isExiting ? 'animate-slide-out-right' : ''}
        transition-all duration-200 ease-apple
        hover:shadow-card-hover
      `}
    >
      <div className="flex gap-3">
        <Icon className={`h-5 w-5 flex-shrink-0 ${styles.icon}`} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100">{toast.title}</p>
          {toast.description && (
            <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">{toast.description}</p>
          )}
          {toast.action && (
            <button
              onClick={toast.action.onClick}
              className="mt-2 text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 transition-colors"
            >
              {toast.action.label}
            </button>
          )}
        </div>
      </div>
      <button
        onClick={handleDismiss}
        className="absolute top-3 right-3 p-1 rounded-full text-neutral-400 hover:text-neutral-600 dark:text-neutral-500 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors"
        aria-label="Dismiss notification"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

export default ToastProvider;
