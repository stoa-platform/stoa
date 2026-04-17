// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package types

// CanonicalAPIVersion is the target version for all STOA resources.
const CanonicalAPIVersion = "gostoa.dev/v1beta1"

// AcceptedAPIVersions lists all apiVersions that stoactl will accept.
// Older versions are transparently upgraded to CanonicalAPIVersion.
var AcceptedAPIVersions = []string{
	"gostoa.dev/v1beta1", // canonical (Phase 4)
	"gostoa.dev/v1",       // MCPServer legacy
	"gostoa.dev/v1alpha1", // CRD legacy (Tool, ToolSet, Skill)
	"stoa.io/v1",          // early prototype — deprecated
}

// IsAcceptedAPIVersion returns true if the given apiVersion is recognized.
func IsAcceptedAPIVersion(v string) bool {
	for _, accepted := range AcceptedAPIVersions {
		if v == accepted {
			return true
		}
	}
	return false
}

// Resource represents a STOA resource (API, Subscription, etc.)
type Resource struct {
	APIVersion string   `yaml:"apiVersion" json:"apiVersion"`
	Kind       string   `yaml:"kind" json:"kind"`
	Metadata   Metadata `yaml:"metadata" json:"metadata"`
	Spec       any      `yaml:"spec" json:"spec"`
}

// Metadata contains resource metadata
type Metadata struct {
	Name      string            `yaml:"name" json:"name"`
	Namespace string            `yaml:"namespace,omitempty" json:"namespace,omitempty"`
	Labels    map[string]string `yaml:"labels,omitempty" json:"labels,omitempty"`
}

// APISpec represents an API resource specification
type APISpec struct {
	Version        string              `yaml:"version,omitempty" json:"version,omitempty"`
	Description    string              `yaml:"description,omitempty" json:"description,omitempty"`
	Upstream       UpstreamSpec        `yaml:"upstream" json:"upstream"`
	Routing        RoutingSpec         `yaml:"routing,omitempty" json:"routing,omitempty"`
	Authentication AuthenticationSpec  `yaml:"authentication,omitempty" json:"authentication,omitempty"`
	Policies       PoliciesSpec        `yaml:"policies,omitempty" json:"policies,omitempty"`
	Catalog        CatalogSpec         `yaml:"catalog,omitempty" json:"catalog,omitempty"`
}

// UpstreamSpec defines the backend service
type UpstreamSpec struct {
	URL     string `yaml:"url" json:"url"`
	Timeout string `yaml:"timeout,omitempty" json:"timeout,omitempty"`
	Retries int    `yaml:"retries,omitempty" json:"retries,omitempty"`
}

// RoutingSpec defines routing configuration
type RoutingSpec struct {
	Path      string   `yaml:"path" json:"path"`
	StripPath bool     `yaml:"stripPath,omitempty" json:"stripPath,omitempty"`
	Methods   []string `yaml:"methods,omitempty" json:"methods,omitempty"`
}

// AuthenticationSpec defines authentication requirements
type AuthenticationSpec struct {
	Required  bool           `yaml:"required" json:"required"`
	Providers []AuthProvider `yaml:"providers,omitempty" json:"providers,omitempty"`
}

// AuthProvider defines an authentication provider
type AuthProvider struct {
	Type   string `yaml:"type" json:"type"`
	Header string `yaml:"header,omitempty" json:"header,omitempty"`
	Issuer string `yaml:"issuer,omitempty" json:"issuer,omitempty"`
}

// PoliciesSpec defines API policies
type PoliciesSpec struct {
	RateLimit *RateLimitPolicy `yaml:"rateLimit,omitempty" json:"rateLimit,omitempty"`
	CORS      *CORSPolicy      `yaml:"cors,omitempty" json:"cors,omitempty"`
	Cache     *CachePolicy     `yaml:"cache,omitempty" json:"cache,omitempty"`
}

// RateLimitPolicy defines rate limiting
type RateLimitPolicy struct {
	RequestsPerHour int `yaml:"requestsPerHour,omitempty" json:"requestsPerHour,omitempty"`
}

// CORSPolicy defines CORS settings
type CORSPolicy struct {
	Origins []string `yaml:"origins,omitempty" json:"origins,omitempty"`
}

// CachePolicy defines caching settings
type CachePolicy struct {
	Enabled    bool `yaml:"enabled" json:"enabled"`
	TTLSeconds int  `yaml:"ttlSeconds,omitempty" json:"ttlSeconds,omitempty"`
}

// CatalogSpec defines catalog visibility
type CatalogSpec struct {
	Visibility  string   `yaml:"visibility,omitempty" json:"visibility,omitempty"`
	Categories  []string `yaml:"categories,omitempty" json:"categories,omitempty"`
	DisplayName string   `yaml:"displayName,omitempty" json:"displayName,omitempty"`
	Tags        []string `yaml:"tags,omitempty" json:"tags,omitempty"`
	OpenAPISpec string   `yaml:"openapiSpec,omitempty" json:"openapiSpec,omitempty"`
}

// API represents an API as returned by GET /v1/tenants/{tenant_id}/apis[/{api_id}].
// Fields mirror control-plane-api APIResponse (src/routers/apis.py).
type API struct {
	ID              string   `json:"id"`
	TenantID        string   `json:"tenant_id,omitempty"`
	Name            string   `json:"name"`
	DisplayName     string   `json:"display_name,omitempty"`
	Version         string   `json:"version,omitempty"`
	Description     string   `json:"description,omitempty"`
	BackendURL      string   `json:"backend_url,omitempty"`
	Status          string   `json:"status,omitempty"`
	DeployedDev     bool     `json:"deployed_dev,omitempty"`
	DeployedStaging bool     `json:"deployed_staging,omitempty"`
	Tags            []string `json:"tags,omitempty"`
	PortalPromoted  bool     `json:"portal_promoted,omitempty"`
}

// APIListResponse represents the response from GET /v1/tenants/{tenant_id}/apis.
// Mirrors PaginatedResponse[APIResponse] from control-plane-api.
type APIListResponse struct {
	Items    []API `json:"items"`
	Total    int   `json:"total"`
	Page     int   `json:"page,omitempty"`
	PageSize int   `json:"page_size,omitempty"`
}

// Deployment represents a deployment from the STOA API
type Deployment struct {
	ID              string `json:"id"`
	TenantID        string `json:"tenant_id"`
	APIID           string `json:"api_id"`
	APIName         string `json:"api_name"`
	Environment     string `json:"environment"`
	Version         string `json:"version"`
	Status          string `json:"status"`
	DeployedBy      string `json:"deployed_by"`
	CreatedAt       string `json:"created_at"`
	UpdatedAt       string `json:"updated_at"`
	CompletedAt     string `json:"completed_at,omitempty"`
	ErrorMessage    string `json:"error_message,omitempty"`
	RollbackOf      string `json:"rollback_of,omitempty"`
	RollbackVersion string `json:"rollback_version,omitempty"`
	GatewayID       string `json:"gateway_id,omitempty"`
	SpecHash        string `json:"spec_hash,omitempty"`
	CommitSHA       string `json:"commit_sha,omitempty"`
	AttemptCount    int    `json:"attempt_count"`
}

// DeploymentListResponse represents the response from GET /v1/tenants/{id}/deployments
type DeploymentListResponse struct {
	Items    []Deployment `json:"items"`
	Total    int          `json:"total"`
	Page     int          `json:"page"`
	PageSize int          `json:"page_size"`
}

// DeploymentCreate represents the request body for POST /v1/tenants/{id}/deployments
type DeploymentCreate struct {
	APIID       string `json:"api_id"`
	APIName     string `json:"api_name,omitempty"`
	Environment string `json:"environment"`
	Version     string `json:"version"`
	GatewayID   string `json:"gateway_id,omitempty"`
	CommitSHA   string `json:"commit_sha,omitempty"`
}

// Tenant represents a tenant from the STOA API
type Tenant struct {
	ID                 string `json:"id"`
	Name               string `json:"name"`
	DisplayName        string `json:"display_name,omitempty"`
	Description        string `json:"description,omitempty"`
	OwnerEmail         string `json:"owner_email,omitempty"`
	Status             string `json:"status,omitempty"`
	ProvisioningStatus string `json:"provisioning_status,omitempty"`
	APICount           int    `json:"api_count,omitempty"`
	ApplicationCount   int    `json:"application_count,omitempty"`
	CreatedAt          string `json:"created_at,omitempty"`
	UpdatedAt          string `json:"updated_at,omitempty"`
}

// TenantCreate represents the request body for creating a tenant
type TenantCreate struct {
	Name        string `json:"name"`
	DisplayName string `json:"display_name,omitempty"`
	Description string `json:"description,omitempty"`
	OwnerEmail  string `json:"owner_email,omitempty"`
}

// Subscription represents a subscription from the STOA API
type Subscription struct {
	ID           string `json:"id"`
	APIID        string `json:"api_id,omitempty"`
	APIName      string `json:"api_name,omitempty"`
	PlanID       string `json:"plan_id,omitempty"`
	PlanName     string `json:"plan_name,omitempty"`
	TenantID     string `json:"tenant_id,omitempty"`
	Status       string `json:"status,omitempty"`
	SubscriberID string `json:"subscriber_id,omitempty"`
	CreatedAt    string `json:"created_at,omitempty"`
	UpdatedAt    string `json:"updated_at,omitempty"`
}

// SubscriptionListResponse represents the response from listing subscriptions
type SubscriptionListResponse struct {
	Items    []Subscription `json:"items"`
	Total    int            `json:"total"`
	Page     int            `json:"page"`
	PageSize int            `json:"page_size"`
}

// GatewayInstance represents a gateway instance from the STOA API
type GatewayInstance struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	DisplayName string `json:"display_name,omitempty"`
	GatewayType string `json:"gateway_type,omitempty"`
	BaseURL     string `json:"base_url,omitempty"`
	Environment string `json:"environment,omitempty"`
	Status      string `json:"status,omitempty"`
	TenantID    string `json:"tenant_id,omitempty"`
	CreatedAt   string `json:"created_at,omitempty"`
	UpdatedAt   string `json:"updated_at,omitempty"`
}

// GatewayListResponse represents the response from listing gateways
type GatewayListResponse struct {
	Items    []GatewayInstance `json:"items"`
	Total    int               `json:"total"`
	Page     int               `json:"page"`
	PageSize int               `json:"page_size"`
}

// GatewayHealthResponse represents the health status of a gateway
type GatewayHealthResponse struct {
	Status  string `json:"status"`
	Version string `json:"version,omitempty"`
	Uptime  string `json:"uptime,omitempty"`
}

// ---- Catalog Sync Types (CAB-2021) ----

// SyncTriggerResponse is the response from POST /v1/admin/catalog/sync
type SyncTriggerResponse struct {
	Status  string `json:"status"`
	Message string `json:"message"`
	SyncID  string `json:"sync_id,omitempty"`
}

// SyncStatusResponse is the response from GET /v1/admin/catalog/sync/status
type SyncStatusResponse struct {
	ID           string `json:"id"`
	SyncType     string `json:"sync_type"`
	Status       string `json:"status"` // running, success, failed
	ItemsSynced  int    `json:"items_synced"`
	ItemsFailed  int    `json:"items_failed"`
	Duration     string `json:"duration,omitempty"`
	ErrorMessage string `json:"error_message,omitempty"`
	StartedAt    string `json:"started_at,omitempty"`
	CompletedAt  string `json:"completed_at,omitempty"`
}

// CatalogStatsResponse is the response from GET /v1/admin/catalog/stats
type CatalogStatsResponse struct {
	TotalAPIs       int                `json:"total_apis"`
	PublishedAPIs   int                `json:"published_apis"`
	UnpublishedAPIs int                `json:"unpublished_apis"`
	ByTenant        map[string]int     `json:"by_tenant"`
	ByCategory      map[string]int     `json:"by_category"`
	LastSync        *SyncStatusResponse `json:"last_sync,omitempty"`
}

// AdminAPI is a single API in the cross-tenant admin listing
type AdminAPI struct {
	ID          string   `json:"id"`
	TenantID    string   `json:"tenant_id"`
	Name        string   `json:"name"`
	DisplayName string   `json:"display_name"`
	Version     string   `json:"version"`
	Description string   `json:"description"`
	Status      string   `json:"status"`
	Tags        []string `json:"tags"`
}

// AdminAPIPaginatedResponse is the response from GET /v1/admin/catalog/apis
type AdminAPIPaginatedResponse struct {
	Items    []AdminAPI `json:"items"`
	Total    int        `json:"total"`
	Page     int        `json:"page"`
	PageSize int        `json:"page_size"`
}

// SyncHistoryResponse is the response from GET /v1/admin/catalog/sync/history
type SyncHistoryResponse struct {
	Syncs []SyncStatusResponse `json:"syncs"`
	Total int                  `json:"total"`
}

// ---- Audit Types (CAB-2022) ----

// AuditEntry represents a single audit log entry
type AuditEntry struct {
	ID           string         `json:"id"`
	Timestamp    string         `json:"timestamp"`
	TenantID     string         `json:"tenant_id"`
	UserID       string         `json:"user_id,omitempty"`
	UserEmail    string         `json:"user_email,omitempty"`
	Action       string         `json:"action"`
	ResourceType string         `json:"resource_type"`
	ResourceID   string         `json:"resource_id,omitempty"`
	Status       string         `json:"status"`
	ClientIP     string         `json:"client_ip,omitempty"`
	UserAgent    string         `json:"user_agent,omitempty"`
	Details      map[string]any `json:"details,omitempty"`
	RequestID    string         `json:"request_id,omitempty"`
}

// AuditListResponse is the response from GET /v1/audit/{tenant_id}
type AuditListResponse struct {
	Entries  []AuditEntry `json:"entries"`
	Total    int          `json:"total"`
	Page     int          `json:"page"`
	PageSize int          `json:"page_size"`
	HasMore  bool         `json:"has_more"`
}

// ---- Consumer Types (CAB-2053) ----

// Consumer represents a consumer from the STOA API
type Consumer struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	DisplayName string `json:"display_name,omitempty"`
	Email       string `json:"email,omitempty"`
	TenantID    string `json:"tenant_id,omitempty"`
	Status      string `json:"status,omitempty"`
	CreatedAt   string `json:"created_at,omitempty"`
	UpdatedAt   string `json:"updated_at,omitempty"`
}

// ConsumerListResponse represents the response from listing consumers
type ConsumerListResponse struct {
	Items []Consumer `json:"items"`
	Total int        `json:"total"`
}

// ---- Contract Types (CAB-2053) ----

// Contract represents a Universal API Contract from the STOA API
type Contract struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	DisplayName string `json:"display_name,omitempty"`
	Description string `json:"description,omitempty"`
	Version     string `json:"version,omitempty"`
	Status      string `json:"status,omitempty"`
	TenantID    string `json:"tenant_id,omitempty"`
	CreatedAt   string `json:"created_at,omitempty"`
	UpdatedAt   string `json:"updated_at,omitempty"`
}

// ContractListResponse represents the response from listing contracts
type ContractListResponse struct {
	Items []Contract `json:"items"`
	Total int        `json:"total"`
}

// ---- Service Account Types (CAB-2053) ----

// ServiceAccount represents a service account from the STOA API
type ServiceAccount struct {
	ID        string `json:"id"`
	Name      string `json:"name"`
	ClientID  string `json:"client_id,omitempty"`
	Status    string `json:"status,omitempty"`
	CreatedAt string `json:"created_at,omitempty"`
}

// ---- Environment Types (CAB-2053) ----

// Environment represents an environment from the STOA API
type Environment struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	DisplayName string `json:"display_name,omitempty"`
	Type        string `json:"type,omitempty"`
	URL         string `json:"url,omitempty"`
	Status      string `json:"status,omitempty"`
}

// EnvironmentListResponse represents the response from listing environments
type EnvironmentListResponse struct {
	Items []Environment `json:"items"`
}

// ---- Plan Types (CAB-2053) ----

// Plan represents a subscription plan from the STOA API
type Plan struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Slug        string `json:"slug,omitempty"`
	DisplayName string `json:"display_name,omitempty"`
	Description string `json:"description,omitempty"`
	TenantID    string `json:"tenant_id,omitempty"`
	Status      string `json:"status,omitempty"`
	CreatedAt   string `json:"created_at,omitempty"`
	UpdatedAt   string `json:"updated_at,omitempty"`
}

// PlanListResponse represents the response from listing plans
type PlanListResponse struct {
	Items []Plan `json:"items"`
	Total int    `json:"total"`
}

// ---- Webhook Types (CAB-2053) ----

// Webhook represents a webhook configuration from the STOA API
type Webhook struct {
	ID        string   `json:"id"`
	Name      string   `json:"name"`
	URL       string   `json:"url"`
	Events    []string `json:"events,omitempty"`
	TenantID  string   `json:"tenant_id,omitempty"`
	Enabled   bool     `json:"enabled"`
	CreatedAt string   `json:"created_at,omitempty"`
}

// WebhookListResponse represents the response from listing webhooks
type WebhookListResponse struct {
	Items []Webhook `json:"items"`
	Total int       `json:"total"`
}
