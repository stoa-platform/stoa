// Package adapters provides per-gateway discovery and policy sync implementations.
package adapters

import (
	"context"
	"time"
)

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
	ID           string   `json:"id"`
	DeploymentID string   `json:"deployment_id,omitempty"`
	Name         string   `json:"name"`
	TenantID     string   `json:"tenant_id"`
	PathPrefix   string   `json:"path_prefix"`
	BackendURL   string   `json:"backend_url"`
	Methods      []string `json:"methods,omitempty"`
	SpecHash     string   `json:"spec_hash,omitempty"`
	OpenAPISpec  []byte   `json:"openapi_spec,omitempty"`
	Activated    bool     `json:"activated"`
}

// Credential represents a consumer credential fetched from Vault for injection.
type Credential struct {
	ConsumerID string `json:"consumer_id"`
	APIName    string `json:"api_name"`
	AuthType   string `json:"auth_type"` // key-auth, oauth2, basic-auth
	Key        string `json:"key"`
	Secret     string `json:"secret,omitempty"`
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

	// InjectCredentials provisions consumer credentials on the local gateway.
	InjectCredentials(ctx context.Context, adminURL string, creds []Credential) error
}

// TelemetryEvent represents a normalized API invocation event (common schema).
type TelemetryEvent struct {
	Timestamp time.Time `json:"timestamp"`
	Method    string    `json:"method"`
	Path      string    `json:"path"`
	Status    int       `json:"status"`
	LatencyMs int64     `json:"latency_ms"`
	TenantID  string    `json:"tenant_id,omitempty"`
	APIName   string    `json:"api_name,omitempty"`
	APIID     string    `json:"api_id,omitempty"`
}

// AuthServerSpec describes an OIDC auth server alias for gateways that support OIDC.
type AuthServerSpec struct {
	Name             string   `json:"name"`
	Description      string   `json:"description,omitempty"`
	DiscoveryURL     string   `json:"discovery_url"`
	IntrospectionURL string   `json:"introspection_url,omitempty"`
	ClientID         string   `json:"client_id"`
	ClientSecret     string   `json:"client_secret,omitempty"`
	Scopes           []string `json:"scopes,omitempty"`
}

// StrategySpec describes an OAuth2 strategy linked to an auth server.
type StrategySpec struct {
	Name            string `json:"name"`
	Description     string `json:"description,omitempty"`
	Type            string `json:"type,omitempty"`   // default: OAUTH2
	AuthServerAlias string `json:"auth_server_alias"`
	ClientID        string `json:"client_id,omitempty"`
	Audience        string `json:"audience"` // CRITICAL: empty string, not omitted
}

// ScopeSpec describes a scope mapping for an OIDC-enabled gateway.
type ScopeSpec struct {
	ScopeName       string   `json:"scope_name"`       // format: {Alias}:{Scope}
	Description     string   `json:"description,omitempty"`
	Audience        string   `json:"audience"`          // CRITICAL: empty string, not omitted
	APIIDs          []string `json:"api_ids,omitempty"`
	AuthServerAlias string   `json:"auth_server_alias"`
	KeycloakScope   string   `json:"keycloak_scope,omitempty"` // default: openid
}

// AliasSpec describes an endpoint alias for gateways that support aliases.
type AliasSpec struct {
	Name                string `json:"name"`
	Description         string `json:"description,omitempty"`
	Type                string `json:"type,omitempty"` // endpoint, authServerAlias
	EndpointURI         string `json:"endpoint_uri"`
	ConnectionTimeout   int    `json:"connection_timeout,omitempty"`
	ReadTimeout         int    `json:"read_timeout,omitempty"`
	Optimization        string `json:"optimization,omitempty"`
	PassSecurityHeaders bool   `json:"pass_security_headers,omitempty"`
}

// OIDCAdapter extends GatewayAdapter for OIDC-capable gateways.
type OIDCAdapter interface {
	UpsertAuthServer(ctx context.Context, adminURL string, spec AuthServerSpec) error
	UpsertStrategy(ctx context.Context, adminURL string, spec StrategySpec) error
	UpsertScope(ctx context.Context, adminURL string, spec ScopeSpec) error
	DeleteAuthServer(ctx context.Context, adminURL string, name string) error
}

// AliasAdapter extends GatewayAdapter for alias-capable gateways.
type AliasAdapter interface {
	UpsertAlias(ctx context.Context, adminURL string, spec AliasSpec) error
	DeleteAlias(ctx context.Context, adminURL string, name string) error
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
