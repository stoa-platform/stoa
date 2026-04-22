package connect

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

func TestResolveAdapterExplicit(t *testing.T) {
	tests := []struct {
		gwType       string
		expectedName string
	}{
		{"kong", "kong"},
		{"gravitee", "gravitee"},
		{"webmethods", "webmethods"},
		{"Kong", "kong"},
		{"GRAVITEE", "gravitee"},
	}

	for _, tt := range tests {
		t.Run(tt.gwType, func(t *testing.T) {
			adapter, name, err := ResolveAdapter(context.Background(), DiscoveryConfig{
				GatewayType:   tt.gwType,
				AdapterConfig: adapters.AdapterConfig{},
			})
			if err != nil {
				t.Fatalf("resolve error: %v", err)
			}
			if adapter == nil {
				t.Fatal("expected non-nil adapter")
			}
			if name != tt.expectedName {
				t.Errorf("expected name %s, got %s", tt.expectedName, name)
			}
		})
	}
}

func TestResolveAdapterUnsupported(t *testing.T) {
	_, _, err := ResolveAdapter(context.Background(), DiscoveryConfig{
		GatewayType: "unknown-gateway",
	})
	if err == nil {
		t.Fatal("expected error for unsupported gateway type")
	}
}

func TestResolveAdapterAutoDetectKong(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"tagline": "Welcome to kong"})
	}))
	defer server.Close()

	adapter, name, err := ResolveAdapter(context.Background(), DiscoveryConfig{
		GatewayAdminURL: server.URL,
		GatewayType:     "auto",
		AdapterConfig:   adapters.AdapterConfig{},
	})
	if err != nil {
		t.Fatalf("resolve error: %v", err)
	}
	if adapter == nil {
		t.Fatal("expected non-nil adapter")
	}
	if name != "kong" {
		t.Errorf("expected kong, got %s", name)
	}
}

func TestResolveAdapterAutoDetectFails(t *testing.T) {
	// Server that doesn't match any gateway
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	_, _, err := ResolveAdapter(context.Background(), DiscoveryConfig{
		GatewayAdminURL: server.URL,
		GatewayType:     "auto",
		AdapterConfig:   adapters.AdapterConfig{},
	})
	if err == nil {
		t.Fatal("expected error when no gateway detected")
	}
}

func TestDiscoveryConfigFromEnv(t *testing.T) {
	t.Setenv("STOA_GATEWAY_ADMIN_URL", "http://kong:8001")
	t.Setenv("STOA_GATEWAY_TYPE", "kong")
	t.Setenv("STOA_GATEWAY_ADMIN_TOKEN", "my-token")
	t.Setenv("STOA_GATEWAY_ADMIN_USER", "admin")
	t.Setenv("STOA_GATEWAY_ADMIN_PASSWORD", "pass")
	t.Setenv("STOA_DISCOVERY_INTERVAL", "30s")

	cfg := DiscoveryConfigFromEnv()

	if cfg.GatewayAdminURL != "http://kong:8001" {
		t.Errorf("expected http://kong:8001, got %s", cfg.GatewayAdminURL)
	}
	if cfg.GatewayType != "kong" {
		t.Errorf("expected kong, got %s", cfg.GatewayType)
	}
	if cfg.AdapterConfig.Token != "my-token" {
		t.Errorf("expected my-token, got %s", cfg.AdapterConfig.Token)
	}
	if cfg.AdapterConfig.Username != "admin" {
		t.Errorf("expected admin, got %s", cfg.AdapterConfig.Username)
	}
	if cfg.AdapterConfig.Password != "pass" {
		t.Errorf("expected pass, got %s", cfg.AdapterConfig.Password)
	}
	if cfg.Interval != 30*time.Second {
		t.Errorf("expected 30s, got %v", cfg.Interval)
	}
}

func TestDiscoveryConfigFromEnvDefaults(t *testing.T) {
	t.Setenv("STOA_GATEWAY_ADMIN_URL", "")
	t.Setenv("STOA_GATEWAY_TYPE", "")
	t.Setenv("STOA_DISCOVERY_INTERVAL", "")
	t.Setenv("STOA_GATEWAY_ADMIN_TOKEN", "")
	t.Setenv("STOA_GATEWAY_ADMIN_USER", "")
	t.Setenv("STOA_GATEWAY_ADMIN_PASSWORD", "")

	cfg := DiscoveryConfigFromEnv()

	if cfg.GatewayType != "auto" {
		t.Errorf("expected default auto, got %s", cfg.GatewayType)
	}
	if cfg.Interval != 60*time.Second {
		t.Errorf("expected default 60s, got %v", cfg.Interval)
	}
}

func TestStartDiscoverySkipsWhenNoURL(t *testing.T) {
	agent := New(Config{
		ControlPlaneURL: "http://localhost",
		GatewayAPIKey:   "key",
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Should not panic or start goroutine
	agent.StartDiscovery(ctx, DiscoveryConfig{})
}

func TestRunDiscoveryReportsToCP(t *testing.T) {
	var discoveryReceived bool
	var discoveryPayload DiscoveryPayload

	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/internal/gateways/gw-test/discovery" {
			discoveryReceived = true
			_ = json.NewDecoder(r.Body).Decode(&discoveryPayload)
			w.WriteHeader(http.StatusOK)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer cpServer.Close()

	agent := New(Config{
		ControlPlaneURL: cpServer.URL,
		GatewayAPIKey:   "key",
	})
	agent.state.SetGatewayID("gw-test")

	// Create a mock adapter that returns test data
	gwServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"data": []map[string]interface{}{
				{
					"id":       "svc-1",
					"name":     "test-service",
					"host":     "backend",
					"port":     8080,
					"protocol": "http",
					"enabled":  true,
				},
			},
		})
	}))
	defer gwServer.Close()

	adapter := adapters.NewKongAdapter(adapters.AdapterConfig{})
	agent.runDiscovery(context.Background(), adapter, gwServer.URL)

	if !discoveryReceived {
		t.Error("expected discovery report to be sent to CP")
	}
	if len(discoveryPayload.APIs) != 1 {
		t.Errorf("expected 1 API in payload, got %d", len(discoveryPayload.APIs))
	}
	if agent.DiscoveredAPIsCount() != 1 {
		t.Errorf("expected 1 discovered API, got %d", agent.DiscoveredAPIsCount())
	}
}
