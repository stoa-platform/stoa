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

// DoRaw performs a raw HTTP request and returns the response (caller must close body)
func (c *Client) DoRaw(method, path string, body any) (*http.Response, error) {
	return c.do(method, path, body)
}

// ListAPIs fetches all APIs
func (c *Client) ListAPIs() (*types.APIListResponse, error) {
	resp, err := c.do("GET", "/v1/portal/apis", nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.APIListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// GetAPI fetches a single API by name
func (c *Client) GetAPI(name string) (*types.API, error) {
	resp, err := c.do("GET", fmt.Sprintf("/v1/portal/apis/%s", name), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("api %q not found", name)
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.API
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// CreateOrUpdateAPI creates or updates an API from a resource definition
func (c *Client) CreateOrUpdateAPI(resource *types.Resource) error {
	resp, err := c.do("POST", "/v1/apis", resource)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// DeleteAPI deletes an API by name
func (c *Client) DeleteAPI(name string) error {
	resp, err := c.do("DELETE", fmt.Sprintf("/v1/apis/%s", name), nil)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("api %q not found", name)
	}

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// ValidateResource performs a dry-run validation
func (c *Client) ValidateResource(resource *types.Resource) error {
	resp, err := c.do("POST", "/v1/apis?dryRun=true", resource)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("validation error (%d): %s", resp.StatusCode, string(body))
	}

	return nil
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
