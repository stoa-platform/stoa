package connect

import (
	"context"
	"encoding/json"
	"fmt"
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

func TestRunRouteSyncSendsAckWithDeploymentIDs(t *testing.T) {
	var ackReceived bool
	var ackPayload RouteSyncAckPayload

	routes := []adapters.Route{
		{ID: "r1", Name: "api-a", DeploymentID: "dep-1", PathPrefix: "/a", BackendURL: "http://svc-a:8080", Activated: true},
		{ID: "r2", Name: "api-b", DeploymentID: "dep-2", PathPrefix: "/b", BackendURL: "http://svc-b:8080", Activated: true},
		{ID: "r3", Name: "api-c", PathPrefix: "/c", BackendURL: "http://svc-c:8080", Activated: true}, // no DeploymentID
	}

	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/v1/internal/gateways/routes":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(routes)
		case r.URL.Path == "/v1/internal/gateways/gw-test/route-sync-ack" && r.Method == "POST":
			ackReceived = true
			_ = json.NewDecoder(r.Body).Decode(&ackPayload)
			w.WriteHeader(http.StatusOK)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer cpServer.Close()

	agent := New(Config{
		ControlPlaneURL: cpServer.URL,
		GatewayAPIKey:   "key",
	})
	agent.gatewayID = "gw-test"

	adapter := &mockSyncAdapter{}
	agent.RunRouteSync(context.Background(), adapter, "http://gateway:8001")

	if !ackReceived {
		t.Fatal("expected route-sync-ack to be sent")
	}
	// Only routes with DeploymentID should be in ack (2 out of 3)
	if len(ackPayload.SyncedRoutes) != 2 {
		t.Errorf("expected 2 ack results (routes with DeploymentID), got %d", len(ackPayload.SyncedRoutes))
	}
	for _, r := range ackPayload.SyncedRoutes {
		if r.Status != "applied" {
			t.Errorf("expected status applied, got %s", r.Status)
		}
	}
}

func TestRunRouteSyncAckReportsFailedStatus(t *testing.T) {
	var ackPayload RouteSyncAckPayload

	routes := []adapters.Route{
		{ID: "r1", Name: "api-a", DeploymentID: "dep-1", PathPrefix: "/a", BackendURL: "http://svc-a:8080", Activated: true},
	}

	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/v1/internal/gateways/routes":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(routes)
		case r.URL.Path == "/v1/internal/gateways/gw-test/route-sync-ack" && r.Method == "POST":
			_ = json.NewDecoder(r.Body).Decode(&ackPayload)
			w.WriteHeader(http.StatusOK)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer cpServer.Close()

	agent := New(Config{
		ControlPlaneURL: cpServer.URL,
		GatewayAPIKey:   "key",
	})
	agent.gatewayID = "gw-test"

	adapter := &mockSyncAdapter{syncRoutesErr: fmt.Errorf("gateway unreachable")}
	agent.RunRouteSync(context.Background(), adapter, "http://gateway:8001")

	if len(ackPayload.SyncedRoutes) != 1 {
		t.Fatalf("expected 1 ack result, got %d", len(ackPayload.SyncedRoutes))
	}
	if ackPayload.SyncedRoutes[0].Status != "failed" {
		t.Errorf("expected status failed, got %s", ackPayload.SyncedRoutes[0].Status)
	}
	if ackPayload.SyncedRoutes[0].Error == "" {
		t.Error("expected error message in failed ack result")
	}
}

func TestRunRouteSyncNoAckWithoutDeploymentIDs(t *testing.T) {
	ackCalled := false

	routes := []adapters.Route{
		{ID: "r1", Name: "api-a", PathPrefix: "/a", BackendURL: "http://svc-a:8080", Activated: true},
	}

	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/v1/internal/gateways/routes":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(routes)
		case "/v1/internal/gateways/gw-test/route-sync-ack":
			ackCalled = true
			w.WriteHeader(http.StatusOK)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer cpServer.Close()

	agent := New(Config{
		ControlPlaneURL: cpServer.URL,
		GatewayAPIKey:   "key",
	})
	agent.gatewayID = "gw-test"

	adapter := &mockSyncAdapter{}
	agent.RunRouteSync(context.Background(), adapter, "http://gateway:8001")

	if ackCalled {
		t.Error("expected no ack call when routes have no DeploymentID")
	}
}

func TestRunRouteSyncIncludesStepsInAck(t *testing.T) {
	var ackPayload RouteSyncAckPayload

	routes := []adapters.Route{
		{ID: "r1", Name: "api-a", DeploymentID: "dep-1", PathPrefix: "/a", BackendURL: "http://svc-a:8080", Activated: true},
	}

	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/v1/internal/gateways/routes":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(routes)
		case r.URL.Path == "/v1/internal/gateways/gw-test/route-sync-ack" && r.Method == "POST":
			_ = json.NewDecoder(r.Body).Decode(&ackPayload)
			w.WriteHeader(http.StatusOK)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer cpServer.Close()

	agent := New(Config{
		ControlPlaneURL: cpServer.URL,
		GatewayAPIKey:   "key",
	})
	agent.gatewayID = "gw-test"

	adapter := &mockSyncAdapter{}
	agent.RunRouteSync(context.Background(), adapter, "http://gateway:8001")

	if len(ackPayload.SyncedRoutes) != 1 {
		t.Fatalf("expected 1 ack result, got %d", len(ackPayload.SyncedRoutes))
	}

	steps := ackPayload.SyncedRoutes[0].Steps
	if len(steps) != 3 {
		t.Fatalf("expected 3 steps, got %d", len(steps))
	}

	expectedNames := []string{"agent_received", "adapter_connected", "api_synced"}
	for i, name := range expectedNames {
		if steps[i].Name != name {
			t.Errorf("step %d: expected name %s, got %s", i, name, steps[i].Name)
		}
		if steps[i].Status != "success" {
			t.Errorf("step %d: expected status success, got %s", i, steps[i].Status)
		}
		if steps[i].StartedAt == "" {
			t.Errorf("step %d: expected non-empty started_at", i)
		}
	}
}

func TestRunRouteSyncStepsShowFailure(t *testing.T) {
	var ackPayload RouteSyncAckPayload

	routes := []adapters.Route{
		{ID: "r1", Name: "api-a", DeploymentID: "dep-1", PathPrefix: "/a", BackendURL: "http://svc-a:8080", Activated: true},
	}

	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/v1/internal/gateways/routes":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(routes)
		case r.URL.Path == "/v1/internal/gateways/gw-test/route-sync-ack" && r.Method == "POST":
			_ = json.NewDecoder(r.Body).Decode(&ackPayload)
			w.WriteHeader(http.StatusOK)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer cpServer.Close()

	agent := New(Config{
		ControlPlaneURL: cpServer.URL,
		GatewayAPIKey:   "key",
	})
	agent.gatewayID = "gw-test"

	adapter := &mockSyncAdapter{syncRoutesErr: fmt.Errorf("gateway unreachable")}
	agent.RunRouteSync(context.Background(), adapter, "http://gateway:8001")

	if len(ackPayload.SyncedRoutes) != 1 {
		t.Fatalf("expected 1 ack result, got %d", len(ackPayload.SyncedRoutes))
	}

	steps := ackPayload.SyncedRoutes[0].Steps
	if len(steps) != 3 {
		t.Fatalf("expected 3 steps, got %d", len(steps))
	}

	// First two steps succeed, api_synced fails
	if steps[0].Status != "success" || steps[1].Status != "success" {
		t.Error("expected first two steps to succeed")
	}
	if steps[2].Name != "api_synced" {
		t.Errorf("expected step 3 name api_synced, got %s", steps[2].Name)
	}
	if steps[2].Status != "failed" {
		t.Errorf("expected step 3 status failed, got %s", steps[2].Status)
	}
	if steps[2].Detail == "" {
		t.Error("expected step 3 detail to contain error message")
	}
}

func TestSyncStepOmittedWhenEmpty(t *testing.T) {
	// Verify omitempty: SyncedRouteResult without steps serializes without "steps" key
	result := SyncedRouteResult{
		DeploymentID: "dep-1",
		Status:       "applied",
	}
	data, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal error: %v", err)
	}
	var m map[string]interface{}
	_ = json.Unmarshal(data, &m)
	if _, ok := m["steps"]; ok {
		t.Error("expected 'steps' key to be omitted when empty")
	}
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
