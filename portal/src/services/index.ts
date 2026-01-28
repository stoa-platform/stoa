// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * STOA Developer Portal - Services
 *
 * Export all service modules for easy imports.
 */

// Control-Plane API Client (for APIs, Applications, Subscriptions)
export { apiClient, setAccessToken, getAccessToken } from './api';

// MCP Gateway Client (for AI agent tool discovery and invocation)
export { mcpClient } from './mcpClient';

// Services
export { apiCatalogService } from './apiCatalog';
export { applicationsService } from './applications';
export { subscriptionsService } from './subscriptions';
export { toolsService } from './tools';
