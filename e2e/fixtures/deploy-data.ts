/**
 * Test data fixtures for Deployment Flow E2E Tests
 */

export const DEPLOY_PAYLOADS = {
  default: {
    api_id: "e2e-petstore-api",
    api_name: "petstore",
    environment: "dev",
    version: "1.0.0-e2e",
  },
} as const;

export const DEPLOY_STATUSES = {
  PENDING: "pending",
  IN_PROGRESS: "in_progress",
  SUCCESS: "success",
  FAILED: "failed",
  ROLLED_BACK: "rolled_back",
} as const;

/** SSE event types emitted during deployment lifecycle */
export const DEPLOY_EVENT_TYPES = [
  "deploy-started",
  "deploy-progress",
  "deploy-success",
  "deploy-failed",
] as const;
