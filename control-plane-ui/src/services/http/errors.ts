import { getFriendlyErrorMessage } from '@stoa/shared/utils';

export function applyFriendlyErrorMessage(error: unknown): void {
  if (error instanceof Error) {
    error.message = getFriendlyErrorMessage(error, error.message);
  }
}
