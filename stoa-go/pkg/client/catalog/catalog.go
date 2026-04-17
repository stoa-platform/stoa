// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package catalog

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"

	"github.com/stoa-platform/stoa-go/pkg/types"
)

// Doer performs HTTP requests. Satisfied by *client.Client.
type Doer interface {
	Do(method, path string, body any) (*http.Response, error)
	TenantID() string
}

// Service provides catalog API operations (list, get, create, delete, validate).
type Service struct {
	doer Doer
}

// New creates a catalog service backed by the given HTTP doer.
func New(doer Doer) *Service {
	return &Service{doer: doer}
}

// apisPath returns the tenant-scoped admin API path. If tenantOverride is
// non-empty (from resource.metadata.namespace, kubectl-style), it wins over
// the client context tenant.
//
// CAB-2095 note: prior versions used the un-scoped `/v1/apis` paths, which
// returned 404 because control-plane-api only mounts the admin CRUD under
// `/v1/tenants/{tenant_id}/apis`. The CLI is the only consumer of these
// methods, so the path change is a bug fix (no external contract to break).
func (s *Service) apisPath(tenantOverride, suffix string) (string, error) {
	tenant := tenantOverride
	if tenant == "" {
		tenant = s.doer.TenantID()
	}
	if tenant == "" {
		return "", fmt.Errorf("no tenant set — use `stoactl config set-context` or metadata.namespace")
	}
	return fmt.Sprintf("/v1/tenants/%s/apis%s", tenant, suffix), nil
}

// apiCreatePayload mirrors control-plane-api/src/routers/apis.py:APICreate.
// The CLI Resource uses nested upstream/catalog specs; the backend expects a
// flat payload, so we translate here.
type apiCreatePayload struct {
	Name        string   `json:"name"`
	DisplayName string   `json:"display_name"`
	Version     string   `json:"version,omitempty"`
	Description string   `json:"description,omitempty"`
	BackendURL  string   `json:"backend_url"`
	OpenAPISpec string   `json:"openapi_spec,omitempty"`
	Tags        []string `json:"tags,omitempty"`
}

func buildAPIPayload(resource *types.Resource) (*apiCreatePayload, error) {
	spec, err := coerceAPISpec(resource.Spec)
	if err != nil {
		return nil, err
	}

	displayName := resource.Metadata.Name
	if spec.Catalog.DisplayName != "" {
		displayName = spec.Catalog.DisplayName
	}

	backendURL := spec.Upstream.URL
	if backendURL == "" {
		return nil, fmt.Errorf("spec.upstream.url is required")
	}

	version := spec.Version
	if version == "" {
		version = "1.0.0"
	}

	tags := append([]string(nil), spec.Catalog.Tags...)

	return &apiCreatePayload{
		Name:        resource.Metadata.Name,
		DisplayName: displayName,
		Version:     version,
		Description: spec.Description,
		BackendURL:  backendURL,
		OpenAPISpec: spec.Catalog.OpenAPISpec,
		Tags:        tags,
	}, nil
}

// coerceAPISpec marshals the Resource.Spec (typed as any after YAML parse)
// through JSON into a strongly-typed APISpec.
func coerceAPISpec(raw any) (*types.APISpec, error) {
	if raw == nil {
		return nil, fmt.Errorf("spec is empty")
	}
	buf, err := json.Marshal(raw)
	if err != nil {
		return nil, fmt.Errorf("marshal spec: %w", err)
	}
	var spec types.APISpec
	if err := json.Unmarshal(buf, &spec); err != nil {
		return nil, fmt.Errorf("unmarshal spec: %w", err)
	}
	return &spec, nil
}

// List fetches all APIs in the current tenant (admin scope).
func (s *Service) List() (*types.APIListResponse, error) {
	path, err := s.apisPath("", "")
	if err != nil {
		return nil, err
	}
	resp, err := s.doer.Do("GET", path, nil)
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

// Get fetches a single API by name in the current tenant.
func (s *Service) Get(name string) (*types.API, error) {
	path, err := s.apisPath("", "/"+name)
	if err != nil {
		return nil, err
	}
	resp, err := s.doer.Do("GET", path, nil)
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

// CreateOrUpdate creates or updates an API from a resource definition.
// Tenant is taken from resource.metadata.namespace first, then the client
// context.
func (s *Service) CreateOrUpdate(resource *types.Resource) error {
	payload, err := buildAPIPayload(resource)
	if err != nil {
		return fmt.Errorf("invalid API spec: %w", err)
	}

	path, err := s.apisPath(resource.Metadata.Namespace, "")
	if err != nil {
		return err
	}

	resp, err := s.doer.Do("POST", path, payload)
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

// Delete deletes an API by name from the current tenant.
func (s *Service) Delete(name string) error {
	path, err := s.apisPath("", "/"+name)
	if err != nil {
		return err
	}
	resp, err := s.doer.Do("DELETE", path, nil)
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

// TriggerSync triggers a catalog sync. If tenantID is non-empty, scopes to that tenant.
func (s *Service) TriggerSync(tenantID string) (*types.SyncTriggerResponse, error) {
	path := "/v1/admin/catalog/sync"
	if tenantID != "" {
		path = fmt.Sprintf("/v1/admin/catalog/sync/tenant/%s", url.PathEscape(tenantID))
	}

	resp, err := s.doer.Do("POST", path, nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.SyncTriggerResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}
	return &result, nil
}

// SyncStatus returns the status of the last sync operation.
func (s *Service) SyncStatus() (*types.SyncStatusResponse, error) {
	resp, err := s.doer.Do("GET", "/v1/admin/catalog/sync/status", nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusNotFound {
		return nil, nil // no sync ever run
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.SyncStatusResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}
	return &result, nil
}

// Stats returns catalog statistics.
func (s *Service) Stats() (*types.CatalogStatsResponse, error) {
	resp, err := s.doer.Do("GET", "/v1/admin/catalog/stats", nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.CatalogStatsResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}
	return &result, nil
}

// ListAllAPIs returns all APIs across tenants (admin view).
func (s *Service) ListAllAPIs(tenantID string, page, pageSize int) (*types.AdminAPIPaginatedResponse, error) {
	params := url.Values{}
	params.Set("page", strconv.Itoa(page))
	params.Set("page_size", strconv.Itoa(pageSize))
	if tenantID != "" {
		params.Set("tenant_id", tenantID)
	}

	resp, err := s.doer.Do("GET", "/v1/admin/catalog/apis?"+params.Encode(), nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error (%d): %s", resp.StatusCode, string(body))
	}

	var result types.AdminAPIPaginatedResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}
	return &result, nil
}

// Validate performs a dry-run validation of an API resource. The backend
// has no dedicated dry-run endpoint, so we validate client-side by building
// the payload — this catches missing required fields before any network call.
func (s *Service) Validate(resource *types.Resource) error {
	if _, err := buildAPIPayload(resource); err != nil {
		return fmt.Errorf("validation error: %w", err)
	}
	return nil
}
