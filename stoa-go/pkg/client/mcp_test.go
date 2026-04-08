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

// --- AC1/AC2/AC3/AC4: ListMCPServers ---

// TestListMCPServers tests AC1: list-servers returns server data (AC18: client method test)
func TestListMCPServers(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("Expected GET request, got %s", r.Method)
		}
		if r.URL.Path != "/v1/admin/mcp/servers" {
			t.Errorf("Expected path /v1/admin/mcp/servers, got %s", r.URL.Path)
		}

		// Verify auth header is set
		if r.Header.Get("Authorization") != "Bearer test-token" {
			t.Errorf("Expected Bearer test-token, got %s", r.Header.Get("Authorization"))
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(types.MCPServerListResponse{
			Servers: []types.MCPServerSummary{
				{
					ID:          "srv-1",
					Name:        "petstore",
					DisplayName: "Petstore MCP",
					Category:    "platform",
					Status:      "active",
					ToolCount:   5,
				},
				{
					ID:          "srv-2",
					Name:        "weather",
					DisplayName: "Weather API",
					Category:    "tenant",
					Status:      "active",
					ToolCount:   2,
				},
			},
			TotalCount: 2,
		})
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")

	resp, err := c.ListMCPServers()
	if err != nil {
		t.Fatalf("ListMCPServers() error = %v", err)
	}
	if resp.TotalCount != 2 {
		t.Errorf("ListMCPServers() total_count = %d, want 2", resp.TotalCount)
	}
	if len(resp.Servers) != 2 {
		t.Errorf("ListMCPServers() servers count = %d, want 2", len(resp.Servers))
	}
	if resp.Servers[0].Name != "petstore" {
		t.Errorf("ListMCPServers() first server name = %q, want %q", resp.Servers[0].Name, "petstore")
	}
	if resp.Servers[0].ToolCount != 5 {
		t.Errorf("ListMCPServers() first server tool_count = %d, want 5", resp.Servers[0].ToolCount)
	}
}

// TestListMCPServersEmpty tests AC2: empty list returns zero servers
func TestListMCPServersEmpty(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(types.MCPServerListResponse{
			Servers:    []types.MCPServerSummary{},
			TotalCount: 0,
		})
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")

	resp, err := c.ListMCPServers()
	if err != nil {
		t.Fatalf("ListMCPServers() error = %v", err)
	}
	if resp.TotalCount != 0 {
		t.Errorf("ListMCPServers() total_count = %d, want 0", resp.TotalCount)
	}
	if len(resp.Servers) != 0 {
		t.Errorf("ListMCPServers() servers count = %d, want 0", len(resp.Servers))
	}
}

// TestListMCPServersError tests error handling for server errors
func TestListMCPServersError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"detail": "internal error"}`))
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")

	_, err := c.ListMCPServers()
	if err == nil {
		t.Error("ListMCPServers() error = nil, want error for 500 response")
	}
}

// --- AC5/AC6/AC7: ListTools ---

// TestListTools tests AC5: list-tools returns tool data (AC18: client method test)
func TestListTools(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("Expected GET request, got %s", r.Method)
		}
		if r.URL.Path != "/v1/admin/mcp/servers/srv-1" {
			t.Errorf("Expected path /v1/admin/mcp/servers/srv-1, got %s", r.URL.Path)
		}

		w.Header().Set("Content-Type", "application/json")
		// Simulate server response with embedded tools
		_ = json.NewEncoder(w).Encode(map[string]any{
			"id":           "srv-1",
			"name":         "petstore",
			"display_name": "Petstore MCP",
			"tools": []map[string]any{
				{
					"name":         "list-pets",
					"display_name": "List Pets",
					"description":  "List all pets",
					"enabled":      true,
				},
				{
					"name":         "get-pet",
					"display_name": "Get Pet",
					"description":  "Get a pet by ID",
					"enabled":      true,
				},
			},
		})
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")

	resp, err := c.ListTools("srv-1")
	if err != nil {
		t.Fatalf("ListTools() error = %v", err)
	}
	if len(resp.Tools) != 2 {
		t.Errorf("ListTools() tools count = %d, want 2", len(resp.Tools))
	}
	if resp.Tools[0].Name != "list-pets" {
		t.Errorf("ListTools() first tool name = %q, want %q", resp.Tools[0].Name, "list-pets")
	}
	if !resp.Tools[0].Enabled {
		t.Error("ListTools() first tool enabled = false, want true")
	}
}

// TestListToolsEmpty tests AC7: empty tools list
func TestListToolsEmpty(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"id":    "srv-1",
			"name":  "empty-server",
			"tools": []map[string]any{},
		})
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")

	resp, err := c.ListTools("srv-1")
	if err != nil {
		t.Fatalf("ListTools() error = %v", err)
	}
	if len(resp.Tools) != 0 {
		t.Errorf("ListTools() tools count = %d, want 0", len(resp.Tools))
	}
}

// TestListToolsServerNotFound tests edge case: server not found
func TestListToolsServerNotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"detail": "Server not found"}`))
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")

	_, err := c.ListTools("nonexistent")
	if err == nil {
		t.Error("ListTools() error = nil, want error for 404 response")
	}
}

// --- AC8/AC9/AC10: CallTool ---

// TestCallTool tests AC8: call tool returns result (AC18: client method test)
func TestCallTool(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("Expected POST request, got %s", r.Method)
		}
		if r.URL.Path != "/v1/admin/mcp/servers/srv-1/tools/invoke" {
			t.Errorf("Expected path /v1/admin/mcp/servers/srv-1/tools/invoke, got %s", r.URL.Path)
		}

		// Verify request body contains tool_name and input
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Errorf("Failed to decode request body: %v", err)
		}
		if body["tool_name"] != "list-pets" {
			t.Errorf("Expected tool_name 'list-pets', got %v", body["tool_name"])
		}
		if body["input"] == nil {
			t.Error("Expected input to be set")
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(types.MCPToolCallResponse{
			Result: json.RawMessage(`{"pets": [{"name": "Fido"}, {"name": "Rex"}]}`),
		})
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")

	input := json.RawMessage(`{"limit": 10}`)
	resp, err := c.CallTool("srv-1", "list-pets", input)
	if err != nil {
		t.Fatalf("CallTool() error = %v", err)
	}
	if resp.Result == nil {
		t.Fatal("CallTool() result = nil, want non-nil")
	}
	if resp.Error != "" {
		t.Errorf("CallTool() error field = %q, want empty", resp.Error)
	}
}

// TestCallToolWithEmptyInput tests edge case: no input defaults to {}
func TestCallToolWithEmptyInput(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Errorf("Failed to decode request body: %v", err)
		}
		// input should be an empty object when nil is passed
		input, ok := body["input"]
		if !ok {
			t.Error("Expected input field in request body")
		}
		inputMap, ok := input.(map[string]any)
		if !ok || len(inputMap) != 0 {
			t.Errorf("Expected empty object for input, got %v", input)
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(types.MCPToolCallResponse{
			Result: json.RawMessage(`{"ok": true}`),
		})
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")

	resp, err := c.CallTool("srv-1", "echo", nil)
	if err != nil {
		t.Fatalf("CallTool() with nil input error = %v", err)
	}
	if resp.Result == nil {
		t.Error("CallTool() result = nil, want non-nil")
	}
}

// TestCallToolError tests error from tool invocation
func TestCallToolError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"detail": "tool execution failed"}`))
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")

	_, err := c.CallTool("srv-1", "fail-tool", json.RawMessage(`{}`))
	if err == nil {
		t.Error("CallTool() error = nil, want error for 500 response")
	}
}

// --- AC11/AC12: MCPHealth ---

// TestMCPHealth tests AC11: health returns status info (AC18: client method test)
func TestMCPHealth(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("Expected GET request, got %s", r.Method)
		}
		if r.URL.Path != "/v1/admin/mcp/servers/health" {
			t.Errorf("Expected path /v1/admin/mcp/servers/health, got %s", r.URL.Path)
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(types.MCPHealthResponse{
			Status:  "healthy",
			Version: "0.42.0",
			Uptime:  "3d 14h 22m",
		})
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")

	resp, err := c.MCPHealth()
	if err != nil {
		t.Fatalf("MCPHealth() error = %v", err)
	}
	if resp.Status != "healthy" {
		t.Errorf("MCPHealth() status = %q, want %q", resp.Status, "healthy")
	}
	if resp.Version != "0.42.0" {
		t.Errorf("MCPHealth() version = %q, want %q", resp.Version, "0.42.0")
	}
	if resp.Uptime != "3d 14h 22m" {
		t.Errorf("MCPHealth() uptime = %q, want %q", resp.Uptime, "3d 14h 22m")
	}
}

// TestMCPHealthUnreachable tests AC12: unreachable endpoint returns error
func TestMCPHealthUnreachable(t *testing.T) {
	// Use a closed server to simulate unreachable endpoint
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")

	_, err := c.MCPHealth()
	if err == nil {
		t.Error("MCPHealth() error = nil, want error for unreachable server")
	}
}

// TestMCPHealthServerError tests 500 response
func TestMCPHealthServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"detail": "service unavailable"}`))
	}))
	defer server.Close()

	c := NewWithConfig(server.URL, "test-tenant", "test-token")

	_, err := c.MCPHealth()
	if err == nil {
		t.Error("MCPHealth() error = nil, want error for 500 response")
	}
}
