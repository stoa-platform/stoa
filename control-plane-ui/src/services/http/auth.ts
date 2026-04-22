export type TokenRefresher = () => Promise<string | null>;

type QueueItem = {
  resolve: (token: string | null) => void;
  reject: (error: unknown) => void;
};

let authToken: string | null = null;
let tokenRefresher: TokenRefresher | null = null;
let isRefreshing = false;
let refreshQueue: QueueItem[] = [];

export function setAuthToken(token: string): void {
  authToken = token;
}

export function getAuthToken(): string | null {
  return authToken;
}

export function clearAuthToken(): void {
  authToken = null;
}

export function setTokenRefresher(refresher: TokenRefresher): void {
  tokenRefresher = refresher;
}

export function getTokenRefresher(): TokenRefresher | null {
  return tokenRefresher;
}

export function getIsRefreshing(): boolean {
  return isRefreshing;
}

export function setIsRefreshing(value: boolean): void {
  isRefreshing = value;
}

export function enqueueRefresh(item: QueueItem): void {
  refreshQueue.push(item);
}

export function drainRefreshQueue(
  outcome: { resolveWith: string | null } | { rejectWith: unknown }
): void {
  if ('resolveWith' in outcome) {
    refreshQueue.forEach(({ resolve }) => resolve(outcome.resolveWith));
  } else {
    refreshQueue.forEach(({ reject }) => reject(outcome.rejectWith));
  }
  refreshQueue = [];
}
