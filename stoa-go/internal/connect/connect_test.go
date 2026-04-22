package connect

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

func TestConfigFromEnv(t *testing.T) {
	t.Setenv("STOA_CONTROL_PLANE_URL", "https://api.test.dev")
	t.Setenv("STOA_GATEWAY_API_KEY", "test-key")
	t.Setenv("STOA_INSTANCE_NAME", "kong-prod-01")
	t.Setenv("STOA_ENVIRONMENT", "staging")
	t.Setenv("STOA_HEARTBEAT_INTERVAL", "10s")

	cfg := ConfigFromEnv("1.0.0")

	if cfg.ControlPlaneURL != "https://api.test.dev" {
		t.Errorf("expected https://api.test.dev, got %s", cfg.ControlPlaneURL)
	}
	if cfg.GatewayAPIKey != "test-key" {
		t.Errorf("expected test-key, got %s", cfg.GatewayAPIKey)
	}
	if cfg.InstanceName != "kong-prod-01" {
		t.Errorf("expected kong-prod-01, got %s", cfg.InstanceName)
	}
	if cfg.Environment != "staging" {
		t.Errorf("expected staging, got %s", cfg.Environment)
	}
	if cfg.HeartbeatInterval != 10*time.Second {
		t.Errorf("expected 10s, got %v", cfg.HeartbeatInterval)
	}
}

func TestConfigFromEnvDefaults(t *testing.T) {
	t.Setenv("STOA_CONTROL_PLANE_URL", "")
	t.Setenv("STOA_GATEWAY_API_KEY", "")
	t.Setenv("STOA_INSTANCE_NAME", "")
	t.Setenv("STOA_ENVIRONMENT", "")
	t.Setenv("STOA_HEARTBEAT_INTERVAL", "")

	cfg := ConfigFromEnv("dev")

	if cfg.Environment != "production" {
		t.Errorf("expected default production, got %s", cfg.Environment)
	}
	if cfg.HeartbeatInterval != 30*time.Second {
		t.Errorf("expected default 30s, got %v", cfg.HeartbeatInterval)
	}
}

func TestIsConfigured(t *testing.T) {
	tests := []struct {
		name     string
		url      string
		key      string
		expected bool
	}{
		{"both set", "https://api.test.dev", "key", true},
		{"no url", "", "key", false},
		{"no key", "https://api.test.dev", "", false},
		{"neither", "", "", false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			a := New(Config{ControlPlaneURL: tt.url, GatewayAPIKey: tt.key})
			if a.IsConfigured() != tt.expected {
				t.Errorf("expected %v, got %v", tt.expected, a.IsConfigured())
			}
		})
	}
}

func TestRegisterSuccess(t *testing.T) {
	var receivedPayload RegistrationPayload
	var receivedKey string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/internal/gateways/register" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		receivedKey = r.Header.Get("X-Gateway-Key")
		if err := json.NewDecoder(r.Body).Decode(&receivedPayload); err != nil {
			t.Errorf("decode payload: %v", err)
		}

		w.WriteHeader(http.StatusCreated)
		if err := json.NewEncoder(w).Encode(RegistrationResponse{
			ID:   "gw-uuid-123",
			Name: "kong-prod-connect",
		}); err != nil {
			t.Errorf("encode response: %v", err)
		}
	}))
	defer server.Close()

	agent := New(Config{
		ControlPlaneURL: server.URL,
		GatewayAPIKey:   "test-api-key",
		InstanceName:    "kong-prod-01",
		Environment:     "production",
		Version:         "0.1.0",
	})

	err := agent.Register(context.Background(), "8090")
	if err != nil {
		t.Fatalf("register failed: %v", err)
	}

	if agent.GatewayID() != "gw-uuid-123" {
		t.Errorf("expected gw-uuid-123, got %s", agent.GatewayID())
	}
	if receivedKey != "test-api-key" {
		t.Errorf("expected X-Gateway-Key test-api-key, got %s", receivedKey)
	}
	if receivedPayload.Mode != "connect" {
		t.Errorf("expected mode connect, got %s", receivedPayload.Mode)
	}
	if receivedPayload.Hostname != "kong-prod-01" {
		t.Errorf("expected hostname kong-prod-01, got %s", receivedPayload.Hostname)
	}
}

func TestRegisterFailure(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"detail":"Invalid gateway key"}`))
	}))
	defer server.Close()

	agent := New(Config{
		ControlPlaneURL: server.URL,
		GatewayAPIKey:   "bad-key",
		InstanceName:    "test",
		Version:         "0.1.0",
	})

	err := agent.Register(context.Background(), "8090")
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if err.Error() == "" {
		t.Error("expected non-empty error message")
	}
}

func TestHeartbeatSuccess(t *testing.T) {
	var receivedKey string
	var heartbeatCalled bool

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/internal/gateways/gw-123/heartbeat" {
			heartbeatCalled = true
			receivedKey = r.Header.Get("X-Gateway-Key")
			w.WriteHeader(http.StatusNoContent)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	agent := New(Config{
		ControlPlaneURL: server.URL,
		GatewayAPIKey:   "hb-key",
	})
	agent.state.SetGatewayID("gw-123")

	err := agent.Heartbeat(context.Background())
	if err != nil {
		t.Fatalf("heartbeat failed: %v", err)
	}
	if !heartbeatCalled {
		t.Error("heartbeat endpoint not called")
	}
	if receivedKey != "hb-key" {
		t.Errorf("expected X-Gateway-Key hb-key, got %s", receivedKey)
	}
}

func TestHeartbeatNotRegistered(t *testing.T) {
	agent := New(Config{ControlPlaneURL: "http://localhost", GatewayAPIKey: "key"})
	err := agent.Heartbeat(context.Background())
	if err == nil {
		t.Fatal("expected error when not registered")
	}
}

// --- CAB-1916: routes_count computed from discovered APIs ---

func TestComputeRoutesCountEmpty(t *testing.T) {
	a := New(Config{ControlPlaneURL: "http://cp", GatewayAPIKey: "key"})
	if got := a.state.ComputeRoutesCount(); got != 0 {
		t.Errorf("computeRoutesCount() = %d, want 0", got)
	}
}

func TestComputeRoutesCountWithPaths(t *testing.T) {
	a := New(Config{ControlPlaneURL: "http://cp", GatewayAPIKey: "key"})
	a.state.SetDiscoveredAPIs([]DiscoveredAPIPayload{
		{Name: "petstore", Paths: []string{"/pets", "/pets/{id}"}, IsActive: true},
		{Name: "payments", Paths: []string{"/charge"}, IsActive: true},
	})
	if got := a.state.ComputeRoutesCount(); got != 3 {
		t.Errorf("computeRoutesCount() = %d, want 3", got)
	}
}

func TestComputeRoutesCountSkipsInactive(t *testing.T) {
	a := New(Config{ControlPlaneURL: "http://cp", GatewayAPIKey: "key"})
	a.state.SetDiscoveredAPIs([]DiscoveredAPIPayload{
		{Name: "active", Paths: []string{"/ok"}, IsActive: true},
		{Name: "inactive", Paths: []string{"/skip1", "/skip2"}, IsActive: false},
	})
	if got := a.state.ComputeRoutesCount(); got != 1 {
		t.Errorf("computeRoutesCount() = %d, want 1", got)
	}
}

func TestComputeRoutesCountNoPaths(t *testing.T) {
	a := New(Config{ControlPlaneURL: "http://cp", GatewayAPIKey: "key"})
	a.state.SetDiscoveredAPIs([]DiscoveredAPIPayload{
		{Name: "minimal", IsActive: true},
	})
	if got := a.state.ComputeRoutesCount(); got != 1 {
		t.Errorf("computeRoutesCount() = %d, want 1 (API with no paths counts as 1)", got)
	}
}

func TestHeartbeatSendsRoutesCount(t *testing.T) {
	var receivedPayload HeartbeatPayload

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := json.NewDecoder(r.Body).Decode(&receivedPayload); err != nil {
			t.Errorf("decode heartbeat: %v", err)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	agent := New(Config{
		ControlPlaneURL: server.URL,
		GatewayAPIKey:   "key",
	})
	agent.state.SetGatewayID("gw-123")
	agent.state.SetDiscoveredAPIs([]DiscoveredAPIPayload{
		{Name: "petstore", Paths: []string{"/pets", "/pets/{id}"}, IsActive: true},
	})

	err := agent.Heartbeat(context.Background())
	if err != nil {
		t.Fatalf("heartbeat failed: %v", err)
	}
	if receivedPayload.RoutesCount != 2 {
		t.Errorf("routes_count = %d, want 2", receivedPayload.RoutesCount)
	}
	if receivedPayload.DiscoveredAPIs != 1 {
		t.Errorf("discovered_apis = %d, want 1", receivedPayload.DiscoveredAPIs)
	}
}

func TestStartHeartbeatStopsOnCancel(t *testing.T) {
	var callCount atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount.Add(1)
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	agent := New(Config{
		ControlPlaneURL:   server.URL,
		GatewayAPIKey:     "key",
		HeartbeatInterval: 50 * time.Millisecond,
	})
	agent.state.SetGatewayID("gw-test")

	ctx, cancel := context.WithCancel(context.Background())
	agent.StartHeartbeat(ctx)

	// Wait for at least 2 heartbeats
	time.Sleep(150 * time.Millisecond)
	cancel()
	time.Sleep(100 * time.Millisecond)

	if callCount.Load() < 2 {
		t.Errorf("expected at least 2 heartbeats, got %d", callCount.Load())
	}
}

// Regression: heartbeat 404 returns ErrGatewayNotFound, enabling re-registration.
func TestHeartbeat404ReturnsNotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"detail":"Gateway instance not found"}`))
	}))
	defer server.Close()

	agent := New(Config{
		ControlPlaneURL: server.URL,
		GatewayAPIKey:   "key",
		InstanceName:    "test-agent",
	})
	agent.state.SetGatewayID("purged-id")

	err := agent.Heartbeat(context.Background())
	if err == nil {
		t.Fatal("expected error on 404 heartbeat")
	}
	if err != ErrGatewayNotFound {
		t.Errorf("expected ErrGatewayNotFound, got: %v", err)
	}
}

// Regression: heartbeat 404 triggers re-registration after 3 consecutive failures.
func TestStartHeartbeat404ReRegisters(t *testing.T) {
	var heartbeatCount atomic.Int32
	var registerCount atomic.Int32

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/internal/gateways/register" {
			registerCount.Add(1)
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(RegistrationResponse{
				ID:   "new-id",
				Name: "re-registered",
			})
			return
		}
		// Heartbeat always returns 404
		heartbeatCount.Add(1)
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	agent := New(Config{
		ControlPlaneURL:   server.URL,
		GatewayAPIKey:     "key",
		InstanceName:      "test-agent",
		HeartbeatInterval: 20 * time.Millisecond,
	})
	agent.state.SetGatewayID("old-purged-id")
	agent.healthPort = "8090"

	ctx, cancel := context.WithCancel(context.Background())
	agent.StartHeartbeat(ctx)

	// Wait for 3 heartbeat 404s + re-registration
	time.Sleep(250 * time.Millisecond)
	cancel()
	time.Sleep(50 * time.Millisecond)

	if registerCount.Load() < 1 {
		t.Errorf("expected at least 1 re-registration, got %d", registerCount.Load())
	}
	if got := agent.state.GatewayID(); got != "new-id" {
		t.Errorf("expected gatewayID=new-id after re-registration, got %s", got)
	}
}
