import {
  createContext,
  useContext,
  useId,
  useLayoutEffect,
  useRef,
  type DialogHTMLAttributes,
  type HTMLAttributes,
} from 'react';
import { createPortal } from 'react-dom';

const TitleContext = createContext('');
const dialogs: HTMLDialogElement[] = [];
const returnTargets = new Map<HTMLDialogElement, HTMLElement | null>();
const toastHosts: HTMLElement[] = [];
const toastHostListeners = new Set<() => void>();
let previousOverflow = '';

/** The topmost open dialog, where notifications stay inside the top layer. */
export function activeToastHost(): HTMLElement | null {
  return toastHosts[toastHosts.length - 1] ?? null;
}

export function subscribeToastHost(listener: () => void): () => void {
  toastHostListeners.add(listener);
  return () => {
    toastHostListeners.delete(listener);
  };
}

function notifyToastHosts() {
  for (const listener of toastHostListeners) listener();
}

interface ModalProps extends Omit<DialogHTMLAttributes<HTMLDialogElement>, 'onClose' | 'open'> {
  'data-testid'?: string;
  open?: boolean;
  onClose: () => void;
  closeDisabled?: boolean;
}

/** Native modal isolation, with explicit focus handling for dynamic content and nested dialogs. */
export function Modal({
  open = true,
  onClose,
  closeDisabled = false,
  children,
  ...props
}: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const latest = useRef({ onClose, closeDisabled });
  useLayoutEffect(() => {
    latest.current = { onClose, closeDisabled };
  });

  useLayoutEffect(() => {
    const dialog = ref.current;
    if (!open || !dialog) return;
    const previousFocus =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const isTop = () => dialogs[dialogs.length - 1] === dialog;
    const focusable = () =>
      Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'a[href], button, input, select, textarea, [tabindex], summary, [contenteditable="true"]'
        )
      ).filter(
        (el) =>
          el.tabIndex >= 0 &&
          !el.matches(':disabled') &&
          !el.closest('[hidden], [inert], [aria-hidden="true"]') &&
          !Array.from(ancestors(el, dialog)).some((parent) => {
            const style = getComputedStyle(parent);
            return style.display === 'none' || style.visibility === 'hidden';
          })
      );
    const focusInitial = () => {
      const target =
        dialog.querySelector<HTMLElement>('[data-autofocus], [autofocus]') ??
        dialog.querySelector<HTMLElement>(`[id="${titleId}"]`) ??
        focusable()[0] ??
        dialog;
      target.focus();
    };
    // Capture the opener before showModal's native autofocus algorithm runs.
    if (!dialogs.length) {
      previousOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
    }
    dialogs.push(dialog);
    returnTargets.set(dialog, previousFocus);
    const host = hostRef.current;
    if (host) {
      toastHosts.push(host);
      notifyToastHosts();
    }
    dialog.showModal();
    focusInitial();

    const keydown = (event: KeyboardEvent) => {
      if (!isTop()) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopImmediatePropagation();
        if (!latest.current.closeDisabled) latest.current.onClose();
      } else if (event.key === 'Tab') {
        const elements = focusable();
        const first = elements[0];
        const last = elements[elements.length - 1];
        const active = document.activeElement;
        if (!first) {
          event.preventDefault();
          dialog.focus();
        } else if (
          !elements.includes(active as HTMLElement) ||
          (event.shiftKey ? active === first : active === last)
        ) {
          event.preventDefault();
          (event.shiftKey ? last : first).focus();
        }
      }
    };
    const focusin = (event: FocusEvent) => {
      if (isTop() && !dialog.contains(event.target as Node)) focusInitial();
    };
    document.addEventListener('keydown', keydown, true);
    document.addEventListener('focusin', focusin);
    return () => {
      document.removeEventListener('keydown', keydown, true);
      document.removeEventListener('focusin', focusin);
      const wasTop = isTop();
      const returnFocus = returnTargets.get(dialog);
      // If an entire dialog subtree unmounts, let its child restore the original opener.
      for (const [child, target] of returnTargets) {
        if (child !== dialog && target && dialog.contains(target))
          returnTargets.set(child, returnFocus ?? null);
      }
      returnTargets.delete(dialog);
      dialogs.splice(dialogs.indexOf(dialog), 1);
      if (host) {
        const hostIndex = toastHosts.indexOf(host);
        if (hostIndex >= 0) toastHosts.splice(hostIndex, 1);
        notifyToastHosts();
      }
      dialog.close();
      if (!dialogs.length) document.body.style.overflow = previousOverflow;
      if (!wasTop) return;
      const parent = dialogs[dialogs.length - 1];
      if (returnFocus?.isConnected && (!parent || parent.contains(returnFocus)))
        returnFocus.focus();
      else if (parent) parent.focus();
      else document.querySelector<HTMLElement>('main[tabindex="-1"]')?.focus();
    };
  }, [open, titleId]);

  if (!open) return null;
  return createPortal(
    <TitleContext.Provider value={titleId}>
      <dialog
        {...props}
        ref={ref}
        data-testid={props['data-testid'] ?? 'accessible-modal'}
        aria-modal="true"
        aria-labelledby={props['aria-label'] ? undefined : titleId}
        tabIndex={-1}
        style={{
          margin: 0,
          border: 0,
          maxWidth: 'none',
          maxHeight: 'none',
          width: '100%',
          height: '100%',
          ...props.style,
        }}
        onCancel={(event) => {
          event.preventDefault();
          if (!latest.current.closeDisabled) latest.current.onClose();
        }}
      >
        {children}
        <div ref={hostRef} data-notification-host="" />
      </dialog>
    </TitleContext.Provider>,
    document.body
  );
}

function* ancestors(element: HTMLElement, boundary: HTMLElement): Generator<HTMLElement> {
  for (
    let parent: HTMLElement | null = element;
    parent && parent !== boundary;
    parent = parent.parentElement
  )
    yield parent;
}

export function ModalTitle({
  as: Heading = 'h2',
  ...props
}: HTMLAttributes<HTMLHeadingElement> & { as?: 'h1' | 'h2' | 'h3' | 'h4' }) {
  const id = useContext(TitleContext);
  return <Heading {...props} id={id} tabIndex={-1} />;
}
