// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package client

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"github.com/stoa-platform/stoa-go/pkg/client/audit"
	"github.com/stoa-platform/stoa-go/pkg/client/catalog"
	"github.com/stoa-platform/stoa-go/pkg/config"
	"github.com/stoa-platform/stoa-go/pkg/keyring"
	"github.com/stoa-platform/stoa-go/pkg/types"
)

// Client represents the STOA API client
type Client struct {
	baseURL    string
	tenant     string
	token      string
	httpClient *http.Client
}

// NewAdmin creates a client using the admin service account token.
// Resolution: STOA_ADMIN_KEY env > keychain "stoactl-admin" context.
func NewAdmin() (*Client, error) {
	cfg, err := config.Load()
	if err != nil {
		return nil, fmt.Errorf("failed to load config: %w", err)
	}

	ctx, err := cfg.GetCurrentContext()
	if err != nil {
		return nil, err
	}

	c := &Client{
		baseURL: ctx.Context.Server,
		tenant:  ctx.Context.Tenant,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}

	if envToken := os.Getenv("STOA_ADMIN_KEY"); envToken != "" {
		c.token = envToken
		return c, nil
	}

	store := keyring.NewOSKeyring()
	tokenData, err := store.Get(ctx.Name + "-admin")
	if err == nil && tokenData != nil && tokenData.ExpiresAt > time.Now().Unix() {
		c.token = tokenData.AccessToken
		return c, nil
	}

	return nil, fmt.Errorf("no admin token found. Set STOA_ADMIN_KEY or run 'stoactl auth login --admin'")
}

// New creates a new STOA API client with token resolution hierarchy:
// 1. STOA_API_KEY env var
// 2. OS Keychain (via go-keyring)
// 3. ~/.stoa/tokens file (deprecated, warns)
func New() (*Client, error) {
	cfg, err := config.Load()
	if err != nil {
		return nil, fmt.Errorf("failed to load config: %w", err)
	}

	ctx, err := cfg.GetCurrentContext()
	if err != nil {
		return nil, err
	}

	client := &Client{
		baseURL: ctx.Context.Server,
		tenant:  ctx.Context.Tenant,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}

	// Token resolution: env > keychain > file (deprecated)
	if envToken := os.Getenv("STOA_API_KEY"); envToken != "" {
		client.token = envToken
		return client, nil
	}

	store := keyring.NewOSKeyring()
	tokenData, err := store.Get(ctx.Name)
	if err == nil && tokenData != nil && tokenData.ExpiresAt > time.Now().Unix() {
		client.token = tokenData.AccessToken
		return client, nil
	}

	// Fallback: file-based token cache (deprecated)
	tokenCache, err := config.LoadTokenCache()
	if err == nil && tokenCache != nil {
		if tokenCache.Context == ctx.Name && tokenCache.ExpiresAt > time.Now().Unix() {
			client.token = tokenCache.AccessToken
			fmt.Fprintf(os.Stderr, "Warning: using deprecated file-based token (~/.stoa/tokens). Run 'stoactl auth login' to migrate to OS Keychain.\n")
		}
	}

	return client, nil
}

// NewForMode returns a client configured for the mode selected by the global
// --admin CLI flag. When admin is true it delegates to NewAdmin (service
// account token, resolved from STOA_ADMIN_KEY or the "<context>-admin" keychain
// entry); otherwise it delegates to New (user OIDC token). Callers should pass
// cmdflags.AdminMode so --admin plumbs through end-to-end (CAB-2107).
func NewForMode(admin bool) (*Client, error) {
	if admin {
		return NewAdmin()
	}
	return New()
}

// NewWithConfig creates a client with specific config
func NewWithConfig(baseURL, tenant, token string) *Client {
	return &Client{
		baseURL: baseURL,
		tenant:  tenant,
		token:   token,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// do performs an HTTP request
func (c *Client) do(method, path string, body any) (*http.Response, error) {
	var bodyReader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal request body: %w", err)
		}
		bodyReader = bytes.NewReader(data)
	}

	url := fmt.Sprintf("%s%s", c.baseURL, path)
	req, err := http.NewRequest(method, url, bodyReader)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	if c.tenant != "" {
		req.Header.Set("X-Tenant-ID", c.tenant)
	}

	if c.token != "" {
		req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.token))
	}

	return c.httpClient.Do(req)
}

// Do performs an HTTP request and returns the response (caller must close body).
// Sub-packages (catalog, audit, trace, quota) use this via the Doer interface.
func (c *Client) Do(method, path string, body any) (*http.Response, error) {
	return c.do(method, path, body)
}

// Catalog returns a catalog sub-client for API operations.
func (c *Client) Catalog() *catalog.Service {
	return catalog.New(c)
}

// Audit returns an audit sub-client for audit log operations.
func (c *Client) Audit() *audit.Service {
	return audit.New(c)
}

// ListAPIs fetches all APIs. Delegates to catalog.Service.
func (c *Client) ListAPIs() (*types.APIListResponse, error) {
	return c.Catalog().List()
}

// GetAPI fetches a single API by name. Delegates to catalog.Service.
func (c *Client) GetAPI(name string) (*types.API, error) {
	return c.Catalog().Get(name)
}

// CreateOrUpdateAPI creates or updates an API. Delegates to catalog.Service.
func (c *Client) CreateOrUpdateAPI(resource *types.Resource) error {
	return c.Catalog().CreateOrUpdate(resource)
}

// DeleteAPI deletes an API by name. Delegates to catalog.Service.
func (c *Client) DeleteAPI(name string) error {
	return c.Catalog().Delete(name)
}

// ValidateResource performs a dry-run validation. Delegates to catalog.Service.
func (c *Client) ValidateResource(resource *types.Resource) error {
	return c.Catalog().Validate(resource)
}

// CreateMCPServer creates an MCP server and returns the server ID
func (c *Client) CreateMCPServer(name, displayName, description string) (string, error) {
	body := map[string]any{
		"name":         name,
		"display_name": displayName,
		"description":  description,
	}

	resp, err := c.do("POST", "/v1/admin/mcp/servers", body)
	if err != nil {
		return "", err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusCreated {
		respBody, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("API error (%d): %s", resp.StatusCode, string(respBody))
	}

	var result struct {
		ID string `json:"id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", fmt.Errorf("failed to decode response: %w", err)
	}

	return result.ID, nil
}

// AddToolToServer registers a tool on an existing MCP server
func (c *Client) AddToolToServer(serverID string, name string, spec types.ToolSpec) error {
	enabled := true
	if spec.Enabled != nil {
		enabled = *spec.Enabled
	}

	body := map[string]any{
		"name":         name,
		"display_name": spec.DisplayName,
		"description":  spec.Description,
		"enabled":      enabled,
	}
	if spec.InputSchema != nil {
		body["input_schema"] = spec.InputSchema
	}

	resp, err := c.do("POST", fmt.Sprintf("/v1/admin/mcp/servers/%s/tools", serverID), body)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusCreated {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(respBody))
	}

	return nil
}

// ListMCPServers lists all registered MCP servers
func (c *Client) ListMCPServers() (*types.MCPServerListResponse, error) {
	resp, err := c.do("GET", "/v1/admin/mcp/servers", nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.MCPServerListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// ListTools lists tools for a specific MCP server
func (c *Client) ListTools(serverID string) (*types.MCPToolListResponse, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/admin/mcp/servers/%s", serverID), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	// Server response includes tools inline
	var serverResp struct {
		Tools []types.MCPToolSummary `json:"tools"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&serverResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &types.MCPToolListResponse{Tools: serverResp.Tools}, nil
}

// CallTool invokes an MCP tool on a specific server
func (c *Client) CallTool(serverID, toolName string, input json.RawMessage) (*types.MCPToolCallResponse, error) {
	if input == nil {
		input = json.RawMessage(`{}`)
	}

	body := map[string]any{
		"tool_name": toolName,
		"input":     json.RawMessage(input),
	}

	resp, err := c.do("POST", fmt.Sprintf("/v1/admin/mcp/servers/%s/tools/invoke", serverID), body)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(respBody))
	}

	var result types.MCPToolCallResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// MCPHealth checks the health of the MCP subsystem
func (c *Client) MCPHealth() (*types.MCPHealthResponse, error) {
	resp, err := c.do("GET", "/v1/admin/mcp/servers/health", nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.MCPHealthResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// ListDeployments lists deployments for the current tenant
func (c *Client) ListDeployments(apiID, environment, status string, page, pageSize int) (*types.DeploymentListResponse, error) {
	path := fmt.Sprintf("/v1/tenants/%s/deployments?page=%d&page_size=%d", c.tenant, page, pageSize)
	if apiID != "" {
		path += "&api_id=" + apiID
	}
	if environment != "" {
		path += "&environment=" + environment
	}
	if status != "" {
		path += "&status=" + status
	}

	resp, err := c.do("GET", path, nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.DeploymentListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// GetDeployment fetches a single deployment by ID
func (c *Client) GetDeployment(deploymentID string) (*types.Deployment, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/tenants/%s/deployments/%s", c.tenant, deploymentID), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("deployment %q not found", deploymentID)
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.Deployment
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// CreateDeployment creates a new deployment
func (c *Client) CreateDeployment(create *types.DeploymentCreate) (*types.Deployment, error) {
	resp, err := c.do("POST", fmt.Sprintf("/v1/tenants/%s/deployments", c.tenant), create)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.Deployment
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// RollbackDeployment triggers a rollback for a deployment
func (c *Client) RollbackDeployment(deploymentID string) (*types.Deployment, error) {
	resp, err := c.do("POST", fmt.Sprintf("/v1/tenants/%s/deployments/%s/rollback", c.tenant, deploymentID), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.Deployment
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// IsAuthenticated checks if the client has a valid token
func (c *Client) IsAuthenticated() bool {
	return c.token != ""
}

// GetBaseURL returns the base URL
func (c *Client) GetBaseURL() string {
	return c.baseURL
}

// TenantID returns the configured tenant identifier
func (c *Client) TenantID() string {
	return c.tenant
}

// ListTenants fetches all tenants
func (c *Client) ListTenants() ([]types.Tenant, error) {
	resp, err := c.do("GET", "/v1/tenants", nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result []types.Tenant
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return result, nil
}

// GetTenant fetches a single tenant by ID
func (c *Client) GetTenant(id string) (*types.Tenant, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/tenants/%s", id), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("tenant %q not found", id)
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.Tenant
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// GetTenantProvisioningStatus polls the async provisioning saga status for a
// tenant (KC group + admin user + policy seed + Kafka events). Returned by
// /v1/tenants/{id}/provisioning-status with fields: tenant_id,
// provisioning_status (pending|provisioning|active|failed), provisioning_error,
// kc_group_id, provisioning_attempts.
func (c *Client) GetTenantProvisioningStatus(id string) (*types.TenantProvisioningStatus, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/tenants/%s/provisioning-status", id), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("tenant %q not found", id)
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.TenantProvisioningStatus
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// CreateTenant creates a new tenant
func (c *Client) CreateTenant(create *types.TenantCreate) (*types.Tenant, error) {
	resp, err := c.do("POST", "/v1/tenants", create)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.Tenant
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// DeleteTenant deletes a tenant by ID
func (c *Client) DeleteTenant(id string) error {
	resp, err := c.do("DELETE", fmt.Sprintf("/v1/tenants/%s", id), nil)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("tenant %q not found", id)
	}

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// ListSubscriptions fetches subscriptions with optional filters
func (c *Client) ListSubscriptions(status string, page, pageSize int) (*types.SubscriptionListResponse, error) {
	path := fmt.Sprintf("/v1/subscriptions?page=%d&page_size=%d", page, pageSize)
	if status != "" {
		path += "&status=" + status
	}

	resp, err := c.do("GET", path, nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.SubscriptionListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// GetSubscription fetches a single subscription by ID
func (c *Client) GetSubscription(id string) (*types.Subscription, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/subscriptions/%s", id), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("subscription %q not found", id)
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.Subscription
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// ApproveSubscription approves a pending subscription
func (c *Client) ApproveSubscription(id string) error {
	resp, err := c.do("POST", fmt.Sprintf("/v1/subscriptions/%s/approve", id), nil)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// RevokeSubscription revokes an active subscription
func (c *Client) RevokeSubscription(id string) error {
	resp, err := c.do("POST", fmt.Sprintf("/v1/subscriptions/%s/revoke", id), nil)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// ListGateways fetches all gateway instances
func (c *Client) ListGateways() (*types.GatewayListResponse, error) {
	resp, err := c.do("GET", "/v1/admin/gateways", nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.GatewayListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// GetGateway fetches a single gateway instance by ID
func (c *Client) GetGateway(id string) (*types.GatewayInstance, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/admin/gateways/%s", id), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("gateway %q not found", id)
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.GatewayInstance
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// GatewayHealth checks the health of a gateway instance
func (c *Client) GatewayHealth(id string) (*types.GatewayHealthResponse, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/admin/gateways/%s/health", id), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.GatewayHealthResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}
