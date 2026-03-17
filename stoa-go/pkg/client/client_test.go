// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package client

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stoa-platform/stoa-go/pkg/types"
)

// TestNewWithConfig tests client creation with specific config
func TestNewWithConfig(t *testing.T) {
	client := NewWithConfig("https://api.stoa.io", "test-tenant", "test-token")

	if client == nil {
		t.Fatal("NewWithConfig() returned nil")
	}

	if client.GetBaseURL() != "https://api.stoa.io" {
		t.Errorf("GetBaseURL() = %q, want %q", client.GetBaseURL(), "https://api.stoa.io")
	}

	if client.TenantID() != "test-tenant" {
		t.Errorf("TenantID() = %q, want %q", client.TenantID(), "test-tenant")
	}

	if !client.IsAuthenticated() {
		t.Error("IsAuthenticated() = false, want true when token is set")
	}
}

// TestNewWithConfigNoToken tests client with no token
func TestNewWithConfigNoToken(t *testing.T) {
	client := NewWithConfig("https://api.stoa.io", "test-tenant", "")

	if client.IsAuthenticated() {
		t.Error("IsAuthenticated() = true, want false when no token")
	}
}

// TestListAPIs tests the ListAPIs method
func TestListAPIs(t *testing.T) {
	// Create mock server
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify request
		if r.Method != http.MethodGet {
			t.Errorf("Expected GET request, got %s", r.Method)
		}
		if r.URL.Path != "/v1/portal/apis" {
			t.Errorf("Expected path /v1/portal/apis, got %s", r.URL.Path)
		}

		// Check headers
		if r.Header.Get("X-Tenant-ID") != "test-tenant" {
			t.Errorf("Expected X-Tenant-ID header 'test-tenant', got %q", r.Header.Get("X-Tenant-ID"))
		}
		if r.Header.Get("Authorization") != "Bearer test-token" {
			t.Errorf("Expected Authorization header 'Bearer test-token', got %q", r.Header.Get("Authorization"))
		}
		if r.Header.Get("Accept") != "application/json" {
			t.Errorf("Expected Accept header 'application/json', got %q", r.Header.Get("Accept"))
		}

		// Send response
		response := types.APIListResponse{
			Items: []types.API{
				{ID: "1", Name: "api-1", Version: "v1", Status: "active"},
				{ID: "2", Name: "api-2", Version: "v2", Status: "inactive"},
			},
			TotalCount: 2,
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(response)
	}))
	defer server.Close()

	client := NewWithConfig(server.URL, "test-tenant", "test-token")

	result, err := client.ListAPIs()
	if err != nil {
		t.Fatalf("ListAPIs() error = %v", err)
	}

	if result.TotalCount != 2 {
		t.Errorf("ListAPIs() TotalCount = %d, want 2", result.TotalCount)
	}

	if len(result.Items) != 2 {
		t.Fatalf("ListAPIs() Items length = %d, want 2", len(result.Items))
	}

	if result.Items[0].Name != "api-1" {
		t.Errorf("ListAPIs() Items[0].Name = %q, want %q", result.Items[0].Name, "api-1")
	}
}

// TestListAPIsError tests error handling for ListAPIs
func TestListAPIsError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("internal server error"))
	}))
	defer server.Close()

	client := NewWithConfig(server.URL, "test-tenant", "test-token")

	_, err := client.ListAPIs()
	if err == nil {
		t.Error("ListAPIs() error = nil, want error for 500 response")
	}
}

// TestGetAPI tests the GetAPI method
func TestGetAPI(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("Expected GET request, got %s", r.Method)
		}
		if r.URL.Path != "/v1/portal/apis/my-api" {
			t.Errorf("Expected path /v1/portal/apis/my-api, got %s", r.URL.Path)
		}

		response := types.API{
			ID:          "123",
			Name:        "my-api",
			Version:     "v1",
			Description: "My test API",
			Status:      "active",
			Upstream:    "https://backend.example.com",
			Path:        "/api/v1",
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(response)
	}))
	defer server.Close()

	client := NewWithConfig(server.URL, "test-tenant", "test-token")

	api, err := client.GetAPI("my-api")
	if err != nil {
		t.Fatalf("GetAPI() error = %v", err)
	}

	if api.Name != "my-api" {
		t.Errorf("GetAPI() Name = %q, want %q", api.Name, "my-api")
	}
	if api.ID != "123" {
		t.Errorf("GetAPI() ID = %q, want %q", api.ID, "123")
	}
	if api.Status != "active" {
		t.Errorf("GetAPI() Status = %q, want %q", api.Status, "active")
	}
}

// TestGetAPINotFound tests 404 handling for GetAPI
func TestGetAPINotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	client := NewWithConfig(server.URL, "test-tenant", "test-token")

	_, err := client.GetAPI("nonexistent")
	if err == nil {
		t.Error("GetAPI() error = nil, want error for 404 response")
	}
}

// TestDeleteAPI tests the DeleteAPI method
func TestDeleteAPI(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			t.Errorf("Expected DELETE request, got %s", r.Method)
		}
		if r.URL.Path != "/v1/apis/my-api" {
			t.Errorf("Expected path /v1/apis/my-api, got %s", r.URL.Path)
		}

		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	client := NewWithConfig(server.URL, "test-tenant", "test-token")

	err := client.DeleteAPI("my-api")
	if err != nil {
		t.Errorf("DeleteAPI() error = %v, want nil", err)
	}
}

// TestDeleteAPINotFound tests 404 handling for DeleteAPI
func TestDeleteAPINotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	client := NewWithConfig(server.URL, "test-tenant", "test-token")

	err := client.DeleteAPI("nonexistent")
	if err == nil {
		t.Error("DeleteAPI() error = nil, want error for 404 response")
	}
}

// TestCreateOrUpdateAPI tests the CreateOrUpdateAPI method
func TestCreateOrUpdateAPI(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("Expected POST request, got %s", r.Method)
		}
		if r.URL.Path != "/v1/apis" {
			t.Errorf("Expected path /v1/apis, got %s", r.URL.Path)
		}
		if r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("Expected Content-Type 'application/json', got %q", r.Header.Get("Content-Type"))
		}

		// Decode and verify the body
		var resource types.Resource
		if err := json.NewDecoder(r.Body).Decode(&resource); err != nil {
			t.Errorf("Failed to decode request body: %v", err)
		}

		if resource.Metadata.Name != "test-api" {
			t.Errorf("Expected resource name 'test-api', got %q", resource.Metadata.Name)
		}

		w.WriteHeader(http.StatusCreated)
	}))
	defer server.Close()

	client := NewWithConfig(server.URL, "test-tenant", "test-token")

	resource := &types.Resource{
		APIVersion: "stoa.io/v1",
		Kind:       "API",
		Metadata: types.Metadata{
			Name: "test-api",
		},
		Spec: map[string]interface{}{
			"version": "v1",
		},
	}

	err := client.CreateOrUpdateAPI(resource)
	if err != nil {
		t.Errorf("CreateOrUpdateAPI() error = %v, want nil", err)
	}
}

// TestValidateResource tests the ValidateResource method (dry-run)
func TestValidateResource(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("Expected POST request, got %s", r.Method)
		}
		if r.URL.Path != "/v1/apis" {
			t.Errorf("Expected path /v1/apis, got %s", r.URL.Path)
		}
		if r.URL.Query().Get("dryRun") != "true" {
			t.Error("Expected dryRun=true query parameter")
		}

		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	client := NewWithConfig(server.URL, "test-tenant", "test-token")

	resource := &types.Resource{
		APIVersion: "stoa.io/v1",
		Kind:       "API",
		Metadata: types.Metadata{
			Name: "test-api",
		},
	}

	err := client.ValidateResource(resource)
	if err != nil {
		t.Errorf("ValidateResource() error = %v, want nil", err)
	}
}

// TestValidateResourceError tests validation failure
func TestValidateResourceError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(`{"error": "invalid spec"}`))
	}))
	defer server.Close()

	client := NewWithConfig(server.URL, "test-tenant", "test-token")

	resource := &types.Resource{
		APIVersion: "stoa.io/v1",
		Kind:       "API",
		Metadata:   types.Metadata{Name: "invalid-api"},
	}

	err := client.ValidateResource(resource)
	if err == nil {
		t.Error("ValidateResource() error = nil, want error for validation failure")
	}
}

// TestCreateMCPServer tests the CreateMCPServer method
func TestCreateMCPServer(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("Expected POST request, got %s", r.Method)
		}
		if r.URL.Path != "/v1/admin/mcp/servers" {
			t.Errorf("Expected path /v1/admin/mcp/servers, got %s", r.URL.Path)
		}

		// Verify request body
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Errorf("Failed to decode request body: %v", err)
		}
		if body["name"] != "petstore-mcp" {
			t.Errorf("Expected name 'petstore-mcp', got %v", body["name"])
		}
		if body["display_name"] != "Petstore MCP" {
			t.Errorf("Expected display_name 'Petstore MCP', got %v", body["display_name"])
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(map[string]string{"id": "srv-123"})
	}))
	defer server.Close()

	client := NewWithConfig(server.URL, "test-tenant", "test-token")

	id, err := client.CreateMCPServer("petstore-mcp", "Petstore MCP", "Auto-bridged from petstore.yaml")
	if err != nil {
		t.Fatalf("CreateMCPServer() error = %v", err)
	}
	if id != "srv-123" {
		t.Errorf("CreateMCPServer() id = %q, want %q", id, "srv-123")
	}
}

// TestCreateMCPServerError tests error handling for CreateMCPServer
func TestCreateMCPServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(`{"detail": "Server with this name already exists"}`))
	}))
	defer server.Close()

	client := NewWithConfig(server.URL, "test-tenant", "test-token")

	_, err := client.CreateMCPServer("duplicate", "Duplicate", "desc")
	if err == nil {
		t.Error("CreateMCPServer() error = nil, want error for 400 response")
	}
}

// TestAddToolToServer tests the AddToolToServer method
func TestAddToolToServer(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("Expected POST request, got %s", r.Method)
		}
		if r.URL.Path != "/v1/admin/mcp/servers/srv-123/tools" {
			t.Errorf("Expected path /v1/admin/mcp/servers/srv-123/tools, got %s", r.URL.Path)
		}

		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Errorf("Failed to decode request body: %v", err)
		}
		if body["name"] != "list-pets" {
			t.Errorf("Expected name 'list-pets', got %v", body["name"])
		}
		if body["display_name"] != "List Pets" {
			t.Errorf("Expected display_name 'List Pets', got %v", body["display_name"])
		}
		if body["enabled"] != true {
			t.Errorf("Expected enabled true, got %v", body["enabled"])
		}
		if body["input_schema"] == nil {
			t.Error("Expected input_schema to be set")
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(map[string]string{"id": "tool-456"})
	}))
	defer server.Close()

	client := NewWithConfig(server.URL, "test-tenant", "test-token")

	enabled := true
	spec := types.ToolSpec{
		DisplayName: "List Pets",
		Description: "List all pets in the store",
		Enabled:     &enabled,
		InputSchema: map[string]any{
			"type":       "object",
			"properties": map[string]any{"limit": map[string]any{"type": "integer"}},
		},
	}

	err := client.AddToolToServer("srv-123", "list-pets", spec)
	if err != nil {
		t.Errorf("AddToolToServer() error = %v, want nil", err)
	}
}

// TestAddToolToServerError tests error handling for AddToolToServer
func TestAddToolToServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("internal server error"))
	}))
	defer server.Close()

	client := NewWithConfig(server.URL, "test-tenant", "test-token")

	spec := types.ToolSpec{
		DisplayName: "Fail Tool",
		Description: "Will fail",
	}

	err := client.AddToolToServer("srv-123", "fail-tool", spec)
	if err == nil {
		t.Error("AddToolToServer() error = nil, want error for 500 response")
	}
}

// TestClientWithoutTenant tests requests without tenant header
func TestClientWithoutTenant(t *testing.T) {
	var receivedTenantHeader string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedTenantHeader = r.Header.Get("X-Tenant-ID")

		response := types.APIListResponse{Items: []types.API{}, TotalCount: 0}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(response)
	}))
	defer server.Close()

	// Create client without tenant
	client := NewWithConfig(server.URL, "", "test-token")

	_, err := client.ListAPIs()
	if err != nil {
		t.Fatalf("ListAPIs() error = %v", err)
	}

	// Tenant header should be empty
	if receivedTenantHeader != "" {
		t.Errorf("Expected no X-Tenant-ID header, got %q", receivedTenantHeader)
	}
}

// TestClientWithoutToken tests requests without auth header
func TestClientWithoutToken(t *testing.T) {
	var receivedAuthHeader string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedAuthHeader = r.Header.Get("Authorization")

		response := types.APIListResponse{Items: []types.API{}, TotalCount: 0}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(response)
	}))
	defer server.Close()

	// Create client without token
	client := NewWithConfig(server.URL, "test-tenant", "")

	_, err := client.ListAPIs()
	if err != nil {
		t.Fatalf("ListAPIs() error = %v", err)
	}

	// Auth header should be empty
	if receivedAuthHeader != "" {
		t.Errorf("Expected no Authorization header, got %q", receivedAuthHeader)
	}
}
