// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package doctor

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestDockerRunningCheck_Name(t *testing.T) {
	c := &DockerRunningCheck{}
	if name := c.Name(); name != "Docker" {
		t.Errorf("Name = %q, want %q", name, "Docker")
	}
}

func TestGatewayHealthCheck_Healthy(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	c := &GatewayHealthCheck{URL: server.URL + "/health"}
	result := c.Run(context.Background())
	if !result.Pass {
		t.Errorf("expected pass, got fail: %s", result.Message)
	}
}

func TestGatewayHealthCheck_Unhealthy(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer server.Close()

	c := &GatewayHealthCheck{URL: server.URL + "/health"}
	result := c.Run(context.Background())
	if result.Pass {
		t.Error("expected fail, got pass")
	}
}

func TestGatewayHealthCheck_Unreachable(t *testing.T) {
	c := &GatewayHealthCheck{URL: "http://127.0.0.1:1/health"}
	result := c.Run(context.Background())
	if result.Pass {
		t.Error("expected fail for unreachable server")
	}
}

func TestPortAvailableCheck_Available(t *testing.T) {
	// Use port 0 which the OS will assign a free port
	c := &PortAvailableCheck{Port: 0}
	result := c.Run(context.Background())
	if !result.Pass {
		t.Errorf("expected port 0 to be available: %s", result.Message)
	}
}

func TestMCPEndpointCheck_Responding(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	c := &MCPEndpointCheck{URL: server.URL + "/mcp/sse"}
	result := c.Run(context.Background())
	if !result.Pass {
		t.Errorf("expected pass, got fail: %s", result.Message)
	}
}

func TestMCPEndpointCheck_NotResponding(t *testing.T) {
	c := &MCPEndpointCheck{URL: "http://127.0.0.1:1/mcp/sse"}
	result := c.Run(context.Background())
	if result.Pass {
		t.Error("expected fail for unreachable endpoint")
	}
}

func TestMCPEndpointCheck_Error(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	c := &MCPEndpointCheck{URL: server.URL + "/mcp/sse"}
	result := c.Run(context.Background())
	if result.Pass {
		t.Error("expected fail for 500 response")
	}
}

func TestKeychainAccessCheck_Name(t *testing.T) {
	c := &KeychainAccessCheck{}
	if name := c.Name(); name != "Keychain" {
		t.Errorf("Name = %q, want %q", name, "Keychain")
	}
}

func TestAPIKeyValidCheck_Name(t *testing.T) {
	c := &APIKeyValidCheck{}
	if name := c.Name(); name != "API key" {
		t.Errorf("Name = %q, want %q", name, "API key")
	}
}

func TestCheckResult(t *testing.T) {
	pass := CheckResult{Pass: true, Message: "ok"}
	if !pass.Pass {
		t.Error("expected Pass=true")
	}

	fail := CheckResult{Pass: false, Message: "failed"}
	if fail.Pass {
		t.Error("expected Pass=false")
	}
}
