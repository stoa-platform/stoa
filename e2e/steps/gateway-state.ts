/**
 * Shared state module for gateway E2E step definitions.
 *
 * Both gateway.steps.ts and gateway-dpop.steps.ts read/write lastResponse
 * through this shared object so that When steps in one module are visible
 * to Then assertion steps in the other.
 */
export const gatewayState = {
  lastResponse: null as { status: number; body: any } | null,
};
