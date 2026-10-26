import type { ButtonHTMLAttributes } from 'react';

/** A native keyboard action inside a table cell, independent of other row actions. */
export function RowAction({
  onActivate,
  children,
  className = '',
  ...props
}: Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onClick' | 'type'> & { onActivate: () => void }) {
  return (
    <button
      {...props}
      type="button"
      data-testid="table-row-action"
      className={`text-left underline underline-offset-2 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-700 dark:focus-visible:outline-primary-300 ${className}`}
      onClick={(event) => {
        event.stopPropagation();
        onActivate();
      }}
    >
      {children}
    </button>
  );
}
