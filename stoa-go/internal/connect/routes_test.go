package connect

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

func TestFetchRoutes(t *testing.T) {
	routes := []adapters.Route{
		{
			ID:         "route-1",
			Name:       "petstore",
			TenantID:   "tenant-a",
			PathPrefix: "/api/pets",
			BackendURL: "http://petstore:8080",
			Methods:    []string{"GET", "POST"},
			Activated:  true,
		},
		{
			ID:         "route-2",
			Name:       "users",
			TenantID:   "tenant-a",
			PathPrefix: "/api/users",
			BackendURL: "http://users:8080",
			Activated:  true,
		},
	}

	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/internal/gateways/routes" && r.Method == "GET" {
			if r.Header.Get("X-Gateway-Key") != "test-key" {
				w.WriteHeader(http.StatusUnauthorized)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(routes)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer cpServer.Close()

	agent := New(Config{
		ControlPlaneURL: cpServer.URL,
		GatewayAPIKey:   "test-key",
		InstanceName:    "test-gw",
	})

	fetched, err := agent.FetchRoutes(context.Background())
	if err != nil {
		t.Fatalf("fetch routes error: %v", err)
	}
	if len(fetched) != 2 {
		t.Fatalf("expected 2 routes, got %d", len(fetched))
	}
	if fetched[0].Name != "petstore" {
		t.Errorf("expected petstore, got %s", fetched[0].Name)
	}
	if fetched[0].BackendURL != "http://petstore:8080" {
		t.Errorf("expected backend http://petstore:8080, got %s", fetched[0].BackendURL)
	}
	if len(fetched[0].Methods) != 2 {
		t.Errorf("expected 2 methods, got %d", len(fetched[0].Methods))
	}
}

func TestFetchRoutesGatewayNameFilter(t *testing.T) {
	var receivedQuery string

	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedQuery = r.URL.Query().Get("gateway_name")
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode([]adapters.Route{})
	}))
	defer cpServer.Close()

	agent := New(Config{
		ControlPlaneURL: cpServer.URL,
		GatewayAPIKey:   "key",
		InstanceName:    "kong-prod-01",
	})

	_, err := agent.FetchRoutes(context.Background())
	if err != nil {
		t.Fatalf("fetch routes error: %v", err)
	}
	if receivedQuery != "kong-prod-01" {
		t.Errorf("expected gateway_name=kong-prod-01, got %s", receivedQuery)
	}
}

func TestFetchRoutesServerError(t *testing.T) {
	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("internal error"))
	}))
	defer cpServer.Close()

	agent := New(Config{
		ControlPlaneURL: cpServer.URL,
		GatewayAPIKey:   "key",
	})

	_, err := agent.FetchRoutes(context.Background())
	if err == nil {
		t.Fatal("expected error on 500 response")
	}
}

func TestRunRouteSyncPushesRoutes(t *testing.T) {
	routes := []adapters.Route{
		{
			ID:         "r1",
			Name:       "api-a",
			PathPrefix: "/a",
			BackendURL: "http://svc-a:8080",
			Activated:  true,
		},
		{
			ID:         "r2",
			Name:       "api-b",
			PathPrefix: "/b",
			BackendURL: "http://svc-b:8080",
			Activated:  true,
		},
	}

	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/internal/gateways/routes" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(routes)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer cpServer.Close()

	agent := New(Config{
		ControlPlaneURL: cpServer.URL,
		GatewayAPIKey:   "key",
		InstanceName:    "test",
	})

	adapter := &mockSyncAdapter{}
	agent.RunRouteSync(context.Background(), adapter, "http://gateway:8001")

	if len(adapter.syncedRoutes) != 2 {
		t.Fatalf("expected 2 synced routes, got %d", len(adapter.syncedRoutes))
	}
	if adapter.syncedRoutes[0].Name != "api-a" {
		t.Errorf("expected api-a, got %s", adapter.syncedRoutes[0].Name)
	}
}

func TestRunRouteSyncNoRoutes(t *testing.T) {
	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode([]adapters.Route{})
	}))
	defer cpServer.Close()

	agent := New(Config{
		ControlPlaneURL: cpServer.URL,
		GatewayAPIKey:   "key",
	})

	adapter := &mockSyncAdapter{}
	agent.RunRouteSync(context.Background(), adapter, "http://gateway:8001")

	if len(adapter.syncedRoutes) != 0 {
		t.Errorf("expected no synced routes, got %d", len(adapter.syncedRoutes))
	}
}

func TestStartRouteSyncSkipsNoURL(t *testing.T) {
	agent := New(Config{
		ControlPlaneURL: "http://localhost",
		GatewayAPIKey:   "key",
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Should not panic
	agent.StartRouteSync(ctx, &mockSyncAdapter{}, "", RouteSyncConfig{})
}

func TestRouteSyncConfigFromEnv(t *testing.T) {
	cfg := RouteSyncConfigFromEnv()
	if cfg.Interval != 30*1e9 { // 30 seconds in nanoseconds
		t.Errorf("expected default 30s interval, got %s", cfg.Interval)
	}

	t.Setenv("STOA_ROUTE_SYNC_INTERVAL", "15s")
	cfg = RouteSyncConfigFromEnv()
	if cfg.Interval != 15*1e9 {
		t.Errorf("expected 15s interval, got %s", cfg.Interval)
	}
}
