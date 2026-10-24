import {
  createContext,
  useContext,
  useId,
  type FormHTMLAttributes,
  type HTMLAttributes,
  type ReactNode,
} from 'react';

const ErrorContext = createContext('');

/** A submission error describes the form; it does not imply that every field is invalid. */
export function Form({
  error,
  children,
  ...props
}: FormHTMLAttributes<HTMLFormElement> & { error?: ReactNode }) {
  const errorId = useId();
  return (
    <ErrorContext.Provider value={errorId}>
      <form
        {...props}
        aria-describedby={
          [props['aria-describedby'], error ? errorId : undefined].filter(Boolean).join(' ') ||
          undefined
        }
      >
        {children}
      </form>
    </ErrorContext.Provider>
  );
}

export function FormError(props: HTMLAttributes<HTMLDivElement>) {
  const id = useContext(ErrorContext);
  return <div {...props} id={id} role="alert" />;
}
