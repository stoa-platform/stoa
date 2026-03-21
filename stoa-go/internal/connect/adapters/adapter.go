// Package adapters provides per-gateway discovery and policy sync implementations.
package adapters

import "context"

// DiscoveredAPI represents an API/service discovered on a gateway.
type DiscoveredAPI struct {
	Name       string   `json:"name"`
	Version    string   `json:"version,omitempty"`
	BackendURL string   `json:"backend_url,omitempty"`
	Paths      []string `json:"paths,omitempty"`
	Methods    []string `json:"methods,omitempty"`
	Policies   []string `json:"policies,omitempty"`
	IsActive   bool     `json:"is_active"`
}

// PolicyAction represents a policy to apply or remove on a gateway.
type PolicyAction struct {
	Type   string                 `json:"type"`
	Config map[string]interface{} `json:"config"`
}

// Route represents an API route fetched from the Control Plane for sync.
type Route struct {
	ID         string   `json:"id"`
	Name       string   `json:"name"`
	TenantID   string   `json:"tenant_id"`
	PathPrefix string   `json:"path_prefix"`
	BackendURL string   `json:"backend_url"`
	Methods    []string `json:"methods,omitempty"`
	SpecHash   string   `json:"spec_hash,omitempty"`
	Activated  bool     `json:"activated"`
}

// GatewayAdapter defines the interface for gateway-specific operations.
type GatewayAdapter interface {
	// Detect checks if the admin URL hosts this gateway type.
	Detect(ctx context.Context, adminURL string) (bool, error)

	// Discover lists all APIs/services registered on the gateway.
	Discover(ctx context.Context, adminURL string) ([]DiscoveredAPI, error)

	// ApplyPolicy pushes a policy to the gateway for a specific API.
	ApplyPolicy(ctx context.Context, adminURL string, apiName string, policy PolicyAction) error

	// RemovePolicy removes a policy from the gateway for a specific API.
	RemovePolicy(ctx context.Context, adminURL string, apiName string, policyType string) error

	// SyncRoutes pushes CP routes to the local gateway.
	SyncRoutes(ctx context.Context, adminURL string, routes []Route) error
}

// AdapterConfig holds common configuration for gateway adapters.
type AdapterConfig struct {
	// Token is the admin API token (e.g., Kong-Admin-Token).
	Token string
	// Username for basic auth (Gravitee, webMethods).
	Username string
	// Password for basic auth.
	Password string
}
