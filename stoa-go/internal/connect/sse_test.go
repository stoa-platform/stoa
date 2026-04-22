package connect

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// mockSSEAdapter captures sync calls for testing.
type mockSSEAdapter struct {
	mu      sync.Mutex
	synced  [][]adapters.Route
	syncErr error
}

func (m *mockSSEAdapter) SyncRoutes(ctx context.Context, adminURL string, routes []adapters.Route) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.synced = append(m.synced, routes)
	return m.syncErr
}

func (m *mockSSEAdapter) Detect(ctx context.Context, adminURL string) (bool, error) {
	return true, nil
}
func (m *mockSSEAdapter) Discover(ctx context.Context, adminURL string) ([]adapters.DiscoveredAPI, error) {
	return nil, nil
}
func (m *mockSSEAdapter) ApplyPolicy(ctx context.Context, adminURL string, apiName string, policy adapters.PolicyAction) error {
	return nil
}
func (m *mockSSEAdapter) RemovePolicy(ctx context.Context, adminURL string, apiName string, policyType string) error {
	return nil
}
func (m *mockSSEAdapter) InjectCredentials(ctx context.Context, adminURL string, creds []adapters.Credential) error {
	return nil
}
func (m *mockSSEAdapter) syncedCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.synced)
}

func TestSSEConfigFromEnv(t *testing.T) {
	// Default
	cfg := SSEConfigFromEnv()
	if cfg.Enabled {
		t.Error("expected SSE disabled by default")
	}
	if cfg.ReconnectInterval != 2*time.Second {
		t.Errorf("expected 2s reconnect, got %s", cfg.ReconnectInterval)
	}

	// Enabled
	t.Setenv("STOA_SSE_ENABLED", "true")
	t.Setenv("STOA_SSE_RECONNECT_INTERVAL", "5s")
	cfg = SSEConfigFromEnv()
	if !cfg.Enabled {
		t.Error("expected SSE enabled")
	}
	if cfg.ReconnectInterval != 5*time.Second {
		t.Errorf("expected 5s reconnect, got %s", cfg.ReconnectInterval)
	}
}

func TestStreamEventsParsesSyncDeployment(t *testing.T) {
	desiredState, _ := json.Marshal(adapters.Route{
		ID:         "route-1",
		Name:       "test-api",
		TenantID:   "acme",
		PathPrefix: "/api/v1",
		BackendURL: "http://backend:8080",
		Activated:  true,
	})

	eventData, _ := json.Marshal(DeploymentEvent{
		DeploymentID:      "dep-123",
		APICatalogID:      "cat-456",
		GatewayInstanceID: "gw-789",
		SyncStatus:        "pending",
		DesiredState:      desiredState,
	})

	// Mock SSE server
	sseServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/internal/gateways/gw-789/events" {
			w.Header().Set("Content-Type", "text/event-stream")
			w.Header().Set("Cache-Control", "no-cache")
			w.WriteHeader(http.StatusOK)
			flusher, ok := w.(http.Flusher)
			if !ok {
				t.Fatal("expected flusher")
			}
			// Send one event then close
			_, _ = fmt.Fprintf(w, "event: sync-deployment\ndata: %s\n\n", string(eventData))
			flusher.Flush()
			return
		}
		// Route sync ack endpoint
		if r.URL.Path == "/v1/internal/gateways/gw-789/route-sync-ack" {
			w.WriteHeader(http.StatusOK)
			return
		}
		// Routes endpoint (for catch-up)
		if r.URL.Path == "/v1/internal/gateways/routes" {
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte("[]"))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer sseServer.Close()

	adapter := &mockSSEAdapter{}
	agent := New(Config{
		ControlPlaneURL: sseServer.URL,
		GatewayAPIKey:   "test-key",
		InstanceName:    "test-gw",
	})
	agent.state.SetGatewayID("gw-789")

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	// Stream should parse the event, sync the route, and ack
	err := agent.streamEvents(ctx, adapter, "http://localhost:8080")

	// Stream ends (server closes connection), expect an error about stream ending
	if err == nil {
		t.Error("expected error when stream ends")
	}

	if adapter.syncedCount() != 1 {
		t.Errorf("expected 1 sync call, got %d", adapter.syncedCount())
	}
}

func TestStreamEventsIgnoresHeartbeat(t *testing.T) {
	sseServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/internal/gateways/gw-1/events" {
			w.Header().Set("Content-Type", "text/event-stream")
			w.WriteHeader(http.StatusOK)
			flusher, _ := w.(http.Flusher)
			_, _ = fmt.Fprintf(w, "event: heartbeat\ndata: {\"status\":\"connected\"}\n\n")
			flusher.Flush()
			return
		}
		if r.URL.Path == "/v1/internal/gateways/routes" {
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte("[]"))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer sseServer.Close()

	adapter := &mockSSEAdapter{}
	agent := New(Config{
		ControlPlaneURL: sseServer.URL,
		GatewayAPIKey:   "test-key",
	})
	agent.state.SetGatewayID("gw-1")

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	_ = agent.streamEvents(ctx, adapter, "http://localhost:8080")

	if adapter.syncedCount() != 0 {
		t.Errorf("expected no sync calls for heartbeat, got %d", adapter.syncedCount())
	}
}

func TestStreamEventsRejectsUnauthorized(t *testing.T) {
	sseServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
	}))
	defer sseServer.Close()

	agent := New(Config{
		ControlPlaneURL: sseServer.URL,
		GatewayAPIKey:   "bad-key",
	})
	agent.state.SetGatewayID("gw-1")

	ctx := context.Background()
	err := agent.streamEvents(ctx, &mockSSEAdapter{}, "http://localhost:8080")

	if err == nil {
		t.Error("expected error for 401")
	}
}

func TestStartDeploymentStreamSkipsWithoutRegistration(t *testing.T) {
	agent := New(Config{})
	// gatewayID is empty — should skip

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Should not panic or start anything
	agent.StartDeploymentStream(ctx, &mockSSEAdapter{}, "http://localhost", SSEConfig{Enabled: true})
}

func TestSSESyncDeploymentIncludesSteps(t *testing.T) {
	desiredState, _ := json.Marshal(adapters.Route{
		ID:         "route-1",
		Name:       "test-api",
		TenantID:   "acme",
		PathPrefix: "/api/v1",
		BackendURL: "http://backend:8080",
		Activated:  true,
	})

	eventData, _ := json.Marshal(DeploymentEvent{
		DeploymentID:      "dep-456",
		APICatalogID:      "cat-789",
		GatewayInstanceID: "gw-sse",
		SyncStatus:        "pending",
		DesiredState:      desiredState,
	})

	var ackPayload RouteSyncAckPayload

	sseServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/internal/gateways/gw-sse/events" {
			w.Header().Set("Content-Type", "text/event-stream")
			w.Header().Set("Cache-Control", "no-cache")
			w.WriteHeader(http.StatusOK)
			flusher, ok := w.(http.Flusher)
			if !ok {
				t.Fatal("expected flusher")
			}
			_, _ = fmt.Fprintf(w, "event: sync-deployment\ndata: %s\n\n", string(eventData))
			flusher.Flush()
			return
		}
		if r.URL.Path == "/v1/internal/gateways/gw-sse/route-sync-ack" && r.Method == "POST" {
			_ = json.NewDecoder(r.Body).Decode(&ackPayload)
			w.WriteHeader(http.StatusOK)
			return
		}
		if r.URL.Path == "/v1/internal/gateways/routes" {
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte("[]"))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer sseServer.Close()

	adapter := &mockSSEAdapter{}
	agent := New(Config{
		ControlPlaneURL: sseServer.URL,
		GatewayAPIKey:   "test-key",
		InstanceName:    "test-gw",
	})
	agent.state.SetGatewayID("gw-sse")

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	_ = agent.streamEvents(ctx, adapter, "http://localhost:8080")

	if len(ackPayload.SyncedRoutes) != 1 {
		t.Fatalf("expected 1 ack result, got %d", len(ackPayload.SyncedRoutes))
	}

	steps := ackPayload.SyncedRoutes[0].Steps
	if len(steps) != 3 {
		t.Fatalf("expected 3 steps (agent_received, adapter_connected, api_synced), got %d", len(steps))
	}

	expectedNames := []string{"agent_received", "adapter_connected", "api_synced"}
	for i, name := range expectedNames {
		if steps[i].Name != name {
			t.Errorf("step %d: expected name %s, got %s", i, name, steps[i].Name)
		}
		if steps[i].Status != "success" {
			t.Errorf("step %d: expected status success, got %s", i, steps[i].Status)
		}
	}
}

func TestMainSSEToggle(t *testing.T) {
	// Verify env var controls SSE vs polling
	_ = os.Unsetenv("STOA_SSE_ENABLED")
	cfg := SSEConfigFromEnv()
	if cfg.Enabled {
		t.Error("SSE should be disabled without env var")
	}

	t.Setenv("STOA_SSE_ENABLED", "true")
	cfg = SSEConfigFromEnv()
	if !cfg.Enabled {
		t.Error("SSE should be enabled with env var")
	}
}
