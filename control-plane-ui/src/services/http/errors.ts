import { getFriendlyErrorMessage } from '@stoa/shared/utils';
import { isRedirecting } from './redirect';

export function applyFriendlyErrorMessage(error: unknown): void {
  // P1-16: while an OIDC redirect is in flight, swallow the friendly
  // transformation so the UI does not show a tech error flash between
  // redirect-initiated and page-unload.
  if (isRedirecting()) return;
  if (error instanceof Error) {
    error.message = getFriendlyErrorMessage(error, error.message);
  }
}
