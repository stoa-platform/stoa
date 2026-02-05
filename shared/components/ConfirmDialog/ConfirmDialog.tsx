import React, { useEffect, useRef, useCallback } from 'react';
import { AlertTriangle, Trash2, X } from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

export type ConfirmVariant = 'default' | 'danger' | 'warning';

export interface ConfirmDialogProps {
  /** Whether the dialog is open */
  open: boolean;
  /** Dialog title */
  title: string;
  /** Dialog message/description */
  message: string;
  /** Label for confirm button */
  confirmLabel?: string;
  /** Label for cancel button */
  cancelLabel?: string;
  /** Variant affects button color */
  variant?: ConfirmVariant;
  /** Show loading state on confirm button */
  loading?: boolean;
  /** Called when user confirms */
  onConfirm: () => void;
  /** Called when user cancels or closes dialog */
  onCancel: () => void;
  /** Custom icon (defaults based on variant) */
  icon?: React.ReactNode;
}

// ============================================================================
// Variant Styles
// ============================================================================

const variantStyles: Record<ConfirmVariant, {
  icon: React.ReactNode;
  iconBg: string;
  iconColor: string;
  confirmButton: string;
}> = {
  default: {
    icon: <AlertTriangle className="h-6 w-6" />,
    iconBg: 'bg-primary-100',
    iconColor: 'text-primary-600',
    confirmButton: 'bg-primary-600 hover:bg-primary-700 text-white',
  },
  danger: {
    icon: <Trash2 className="h-6 w-6" />,
    iconBg: 'bg-error-100',
    iconColor: 'text-error-600',
    confirmButton: 'bg-error-600 hover:bg-error-700 text-white',
  },
  warning: {
    icon: <AlertTriangle className="h-6 w-6" />,
    iconBg: 'bg-warning-100',
    iconColor: 'text-warning-600',
    confirmButton: 'bg-warning-600 hover:bg-warning-700 text-white',
  },
};

// ============================================================================
// Component
// ============================================================================

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  loading = false,
  onConfirm,
  onCancel,
  icon,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const confirmButtonRef = useRef<HTMLButtonElement>(null);
  const styles = variantStyles[variant];

  // Focus trap: focus confirm button when dialog opens
  useEffect(() => {
    if (open && confirmButtonRef.current) {
      confirmButtonRef.current.focus();
    }
  }, [open]);

  // Handle Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open && !loading) {
        onCancel();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, loading, onCancel]);

  // Prevent body scroll when dialog is open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  // Handle backdrop click
  const handleBackdropClick = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget && !loading) {
      onCancel();
    }
  }, [loading, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      aria-describedby="confirm-dialog-description"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 animate-fade-in" />

      {/* Dialog */}
      <div
        ref={dialogRef}
        className="relative bg-white rounded-modal shadow-modal w-full max-w-md animate-scale-in"
      >
        {/* Close button */}
        <button
          onClick={onCancel}
          disabled={loading}
          className="absolute top-4 right-4 p-1 rounded-full text-neutral-400 hover:text-neutral-600 hover:bg-neutral-100 transition-colors disabled:opacity-50"
          aria-label="Close dialog"
        >
          <X className="h-5 w-5" />
        </button>

        {/* Content */}
        <div className="p-6">
          {/* Icon */}
          <div className={`mx-auto w-12 h-12 rounded-full ${styles.iconBg} ${styles.iconColor} flex items-center justify-center mb-4`}>
            {icon || styles.icon}
          </div>

          {/* Title */}
          <h2
            id="confirm-dialog-title"
            className="text-lg font-semibold text-neutral-900 text-center mb-2"
          >
            {title}
          </h2>

          {/* Message */}
          <p
            id="confirm-dialog-description"
            className="text-sm text-neutral-600 text-center"
          >
            {message}
          </p>
        </div>

        {/* Actions */}
        <div className="flex gap-3 px-6 pb-6">
          <button
            onClick={onCancel}
            disabled={loading}
            className="flex-1 px-4 py-2.5 text-sm font-medium text-neutral-700 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50 transition-colors disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmButtonRef}
            onClick={onConfirm}
            disabled={loading}
            className={`flex-1 px-4 py-2.5 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 ${styles.confirmButton}`}
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                    fill="none"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                Processing...
              </span>
            ) : (
              confirmLabel
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Hook for easier usage
// ============================================================================

export interface UseConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: ConfirmVariant;
}

/**
 * Hook to show a confirm dialog and get the result
 * @returns [confirm, ConfirmDialogComponent]
 */
export function useConfirm() {
  const [state, setState] = React.useState<{
    open: boolean;
    options: UseConfirmOptions | null;
    resolve: ((value: boolean) => void) | null;
  }>({
    open: false,
    options: null,
    resolve: null,
  });

  const confirm = useCallback((options: UseConfirmOptions): Promise<boolean> => {
    return new Promise((resolve) => {
      setState({
        open: true,
        options,
        resolve,
      });
    });
  }, []);

  const handleConfirm = useCallback(() => {
    state.resolve?.(true);
    setState({ open: false, options: null, resolve: null });
  }, [state.resolve]);

  const handleCancel = useCallback(() => {
    state.resolve?.(false);
    setState({ open: false, options: null, resolve: null });
  }, [state.resolve]);

  const ConfirmDialogComponent = state.options ? (
    <ConfirmDialog
      open={state.open}
      title={state.options.title}
      message={state.options.message}
      confirmLabel={state.options.confirmLabel}
      cancelLabel={state.options.cancelLabel}
      variant={state.options.variant}
      onConfirm={handleConfirm}
      onCancel={handleCancel}
    />
  ) : null;

  return [confirm, ConfirmDialogComponent] as const;
}

export default ConfirmDialog;
