import {
  createContext,
  useContext,
  useId,
  useState,
  forwardRef,
  type HTMLAttributes,
  type LabelHTMLAttributes,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';

const FieldContext = createContext<{ id: string; errorId?: string }>({ id: '' });

/** Each instance (including repeated rows) owns a unique, stable label/control association. */
export function Field({
  error,
  id,
  children,
  onInvalidCapture,
  onInputCapture,
  ...props
}: HTMLAttributes<HTMLDivElement> & { error?: string }) {
  const generatedId = useId();
  const [validationError, setValidationError] = useState<string>();
  const message = error || validationError;
  const fieldId = id ?? generatedId;
  const errorId = message ? `${fieldId}-error` : undefined;
  return (
    <FieldContext.Provider value={{ id: fieldId, errorId }}>
      <div
        {...props}
        data-testid="accessible-field"
        onInvalidCapture={(event) => {
          const control = event.target;
          if (
            control instanceof HTMLInputElement ||
            control instanceof HTMLSelectElement ||
            control instanceof HTMLTextAreaElement
          )
            setValidationError(control.validationMessage);
          onInvalidCapture?.(event);
        }}
        onInputCapture={(event) => {
          const control = event.target;
          if (
            (control instanceof HTMLInputElement ||
              control instanceof HTMLSelectElement ||
              control instanceof HTMLTextAreaElement) &&
            control.validity.valid
          )
            setValidationError(undefined);
          onInputCapture?.(event);
        }}
      >
        {children}
        {message && (
          <p id={errorId} role="alert" className="mt-1 text-sm text-error-700 dark:text-error-300">
            {message}
          </p>
        )}
      </div>
    </FieldContext.Provider>
  );
}

export function FieldLabel(props: LabelHTMLAttributes<HTMLLabelElement>) {
  const field = useContext(FieldContext);
  return <label {...props} htmlFor={props.htmlFor ?? field.id} />;
}

function useFieldProps(props: {
  id?: string;
  'aria-describedby'?: string;
  'aria-invalid'?: InputHTMLAttributes<HTMLInputElement>['aria-invalid'];
}) {
  const field = useContext(FieldContext);
  return {
    id: props.id ?? field.id,
    'aria-describedby':
      [props['aria-describedby'], field.errorId].filter(Boolean).join(' ') || undefined,
    'aria-invalid': field.errorId ? true : props['aria-invalid'],
  };
}

export const FieldInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function FieldInput(props, ref) {
    const fieldProps = useFieldProps(props);
    return <input {...props} {...fieldProps} ref={ref} />;
  }
);
export const FieldSelect = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function FieldSelect(props, ref) {
    const fieldProps = useFieldProps(props);
    return <select {...props} {...fieldProps} ref={ref} />;
  }
);
export const FieldTextarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function FieldTextarea(props, ref) {
  const fieldProps = useFieldProps(props);
  return <textarea {...props} {...fieldProps} ref={ref} />;
});
