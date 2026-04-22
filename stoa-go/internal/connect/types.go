package connect

import "encoding/json"

// Wire DTOs for the CP Registration Protocol (ADR-057) and SSE deployment
// stream (ADR-059). Struct tags are the source of truth — do not rename a
// `json:"..."` tag without coordinating the corresponding change on the CP
// side (control-plane-api).

// --- Registration (POST /v1/internal/gateways/register) ---

// RegistrationPayload is the payload sent to the register endpoint.
type RegistrationPayload struct {
	Hostname         string   `json:"hostname"`
	Mode             string   `json:"mode"`
	Version          string   `json:"version"`
	Environment      string   `json:"environment"`
	Capabilities     []string `json:"capabilities"`
	AdminURL         string   `json:"admin_url"`
	TargetGatewayURL string   `json:"target_gateway_url,omitempty"`
	PublicURL        string   `json:"public_url,omitempty"`
	UIURL            string   `json:"ui_url,omitempty"`
}

// RegistrationResponse is the response returned by the register endpoint.
type RegistrationResponse struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Environment string `json:"environment"`
	Status      string `json:"status"`
}

// --- Heartbeat (POST /v1/internal/gateways/{id}/heartbeat) ---

// HeartbeatPayload is the payload sent to the heartbeat endpoint.
// PoliciesCount is currently always zero (see REWRITE-BUGS.md F.8).
type HeartbeatPayload struct {
	UptimeSeconds  int `json:"uptime_seconds"`
	RoutesCount    int `json:"routes_count"`
	PoliciesCount  int `json:"policies_count"`
	DiscoveredAPIs int `json:"discovered_apis"`
}

// --- Discovery (POST /v1/internal/gateways/{id}/discovery) ---

// DiscoveryPayload is the payload sent to the discovery endpoint.
type DiscoveryPayload struct {
	APIs []DiscoveredAPIPayload `json:"apis"`
}

// DiscoveredAPIPayload represents a single discovered API for the CP.
type DiscoveredAPIPayload struct {
	Name       string   `json:"name"`
	Version    string   `json:"version,omitempty"`
	BackendURL string   `json:"backend_url,omitempty"`
	Paths      []string `json:"paths,omitempty"`
	Methods    []string `json:"methods,omitempty"`
	Policies   []string `json:"policies,omitempty"`
	IsActive   bool     `json:"is_active"`
}

// --- Gateway config fetch (GET /v1/internal/gateways/{id}/config) ---

// GatewayConfigResponse is the response from the config endpoint.
// PendingDeployments is currently unused by the agent (see REWRITE-BUGS.md F.9).
type GatewayConfigResponse struct {
	GatewayID          string          `json:"gateway_id"`
	Name               string          `json:"name"`
	Environment        string          `json:"environment"`
	TenantID           string          `json:"tenant_id"`
	PendingDeployments []interface{}   `json:"pending_deployments"`
	PendingPolicies    []PendingPolicy `json:"pending_policies"`
}

// PendingPolicy represents a policy returned by the CP config endpoint.
type PendingPolicy struct {
	ID         string                 `json:"id"`
	Name       string                 `json:"name"`
	PolicyType string                 `json:"policy_type"`
	Config     map[string]interface{} `json:"config"`
	Priority   int                    `json:"priority"`
	Enabled    bool                   `json:"enabled"`
}

// --- Policy sync ack (POST /v1/internal/gateways/{id}/sync-ack) ---

// SyncAckPayload is the payload sent to the policy sync-ack endpoint.
type SyncAckPayload struct {
	SyncedPolicies []SyncedPolicyResult `json:"synced_policies"`
	SyncTimestamp  string               `json:"sync_timestamp"`
}

// SyncedPolicyResult reports the sync result for one policy.
type SyncedPolicyResult struct {
	PolicyID string `json:"policy_id"`
	Status   string `json:"status"` // "applied", "removed", "failed"
	Error    string `json:"error,omitempty"`
}

// --- Route sync ack (POST /v1/internal/gateways/{id}/route-sync-ack) ---

// RouteSyncAckPayload is the payload sent to the route-sync-ack endpoint.
type RouteSyncAckPayload struct {
	SyncedRoutes  []SyncedRouteResult `json:"synced_routes"`
	SyncTimestamp string              `json:"sync_timestamp"`
}

// SyncedRouteResult reports the sync result for one route deployment.
type SyncedRouteResult struct {
	DeploymentID string     `json:"deployment_id"`
	Status       string     `json:"status"` // "applied", "failed"
	Error        string     `json:"error,omitempty"`
	Steps        []SyncStep `json:"steps,omitempty"`
	Generation   int        `json:"generation,omitempty"` // CAB-1950: generation that was synced
}

// --- SSE deployment stream (GET /v1/internal/gateways/{id}/events) ---

// SSEEvent is the on-the-wire form of a Server-Sent Event produced by the CP.
type SSEEvent struct {
	Event string          `json:"event"`
	Data  json.RawMessage `json:"data"`
}

// DeploymentEvent is the data payload for a "sync-deployment" SSE event.
type DeploymentEvent struct {
	DeploymentID      string          `json:"deployment_id"`
	APICatalogID      string          `json:"api_catalog_id"`
	GatewayInstanceID string          `json:"gateway_instance_id"`
	SyncStatus        string          `json:"sync_status"`
	DesiredState      json.RawMessage `json:"desired_state"`
}
