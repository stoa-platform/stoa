package connect

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

func TestFetchConfig(t *testing.T) {
	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/internal/gateways/gw-test/config" && r.Method == "GET" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(GatewayConfigResponse{
				GatewayID:   "gw-test",
				Name:        "test-gateway",
				Environment: "dev",
				PendingPolicies: []PendingPolicy{
					{
						ID:         "pol-1",
						Name:       "rate-limit",
						PolicyType: "rate_limit",
						Config:     map[string]interface{}{"requests_per_minute": float64(100)},
						Priority:   10,
						Enabled:    true,
					},
				},
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer cpServer.Close()

	agent := New(Config{
		ControlPlaneURL: cpServer.URL,
		GatewayAPIKey:   "key",
	})
	agent.gatewayID = "gw-test"

	config, err := agent.FetchConfig(context.Background())
	if err != nil {
		t.Fatalf("fetch config error: %v", err)
	}
	if config.GatewayID != "gw-test" {
		t.Errorf("expected gateway_id gw-test, got %s", config.GatewayID)
	}
	if len(config.PendingPolicies) != 1 {
		t.Fatalf("expected 1 policy, got %d", len(config.PendingPolicies))
	}
	if config.PendingPolicies[0].PolicyType != "rate_limit" {
		t.Errorf("expected rate_limit, got %s", config.PendingPolicies[0].PolicyType)
	}
}

func TestFetchConfigNotRegistered(t *testing.T) {
	agent := New(Config{
		ControlPlaneURL: "http://localhost",
		GatewayAPIKey:   "key",
	})

	_, err := agent.FetchConfig(context.Background())
	if err == nil {
		t.Fatal("expected error when not registered")
	}
}

func TestReportSyncAck(t *testing.T) {
	var receivedPayload SyncAckPayload

	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/internal/gateways/gw-test/sync-ack" && r.Method == "POST" {
			_ = json.NewDecoder(r.Body).Decode(&receivedPayload)
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
	agent.gatewayID = "gw-test"

	results := []SyncedPolicyResult{
		{PolicyID: "pol-1", Status: "applied"},
		{PolicyID: "pol-2", Status: "failed", Error: "connection refused"},
	}

	err := agent.ReportSyncAck(context.Background(), results)
	if err != nil {
		t.Fatalf("report sync-ack error: %v", err)
	}
	if len(receivedPayload.SyncedPolicies) != 2 {
		t.Errorf("expected 2 results, got %d", len(receivedPayload.SyncedPolicies))
	}
	if receivedPayload.SyncTimestamp == "" {
		t.Error("expected non-empty sync_timestamp")
	}
}

// mockSyncAdapter implements GatewayAdapter for sync testing.
type mockSyncAdapter struct {
	appliedPolicies   []string
	removedPolicies   []string
	syncedRoutes      []adapters.Route
	injectedCreds     []adapters.Credential
	applyErr          error
	removeErr         error
	syncRoutesErr     error
	injectCredsErr    error
}

func (m *mockSyncAdapter) Detect(ctx context.Context, adminURL string) (bool, error) {
	return true, nil
}

func (m *mockSyncAdapter) Discover(ctx context.Context, adminURL string) ([]adapters.DiscoveredAPI, error) {
	return nil, nil
}

func (m *mockSyncAdapter) ApplyPolicy(ctx context.Context, adminURL string, apiName string, policy adapters.PolicyAction) error {
	m.appliedPolicies = append(m.appliedPolicies, apiName+":"+policy.Type)
	return m.applyErr
}

func (m *mockSyncAdapter) RemovePolicy(ctx context.Context, adminURL string, apiName string, policyType string) error {
	m.removedPolicies = append(m.removedPolicies, apiName+":"+policyType)
	return m.removeErr
}

func (m *mockSyncAdapter) SyncRoutes(ctx context.Context, adminURL string, routes []adapters.Route) error {
	m.syncedRoutes = append(m.syncedRoutes, routes...)
	return m.syncRoutesErr
}

func (m *mockSyncAdapter) InjectCredentials(ctx context.Context, adminURL string, creds []adapters.Credential) error {
	m.injectedCreds = append(m.injectedCreds, creds...)
	return m.injectCredsErr
}

func TestRunSyncAppliesEnabledPolicies(t *testing.T) {
	var ackReceived bool
	var ackPayload SyncAckPayload

	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/v1/internal/gateways/gw-test/config" && r.Method == "GET":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(GatewayConfigResponse{
				GatewayID: "gw-test",
				PendingPolicies: []PendingPolicy{
					{ID: "pol-1", Name: "rate-limit", PolicyType: "rate_limit", Config: map[string]interface{}{"rpm": float64(100)}, Enabled: true},
					{ID: "pol-2", Name: "cors", PolicyType: "cors", Config: map[string]interface{}{"origins": "*"}, Enabled: false},
				},
			})
		case r.URL.Path == "/v1/internal/gateways/gw-test/sync-ack" && r.Method == "POST":
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
	agent.RunSync(context.Background(), adapter, cpServer.URL)

	// Enabled policy should be applied
	if len(adapter.appliedPolicies) != 1 {
		t.Errorf("expected 1 applied policy, got %d", len(adapter.appliedPolicies))
	}
	if len(adapter.appliedPolicies) > 0 && adapter.appliedPolicies[0] != "rate-limit:rate_limit" {
		t.Errorf("expected rate-limit:rate_limit, got %s", adapter.appliedPolicies[0])
	}

	// Disabled policy should be removed
	if len(adapter.removedPolicies) != 1 {
		t.Errorf("expected 1 removed policy, got %d", len(adapter.removedPolicies))
	}
	if len(adapter.removedPolicies) > 0 && adapter.removedPolicies[0] != "cors:cors" {
		t.Errorf("expected cors:cors, got %s", adapter.removedPolicies[0])
	}

	// Sync ack should be sent
	if !ackReceived {
		t.Error("expected sync-ack to be sent")
	}
	if len(ackPayload.SyncedPolicies) != 2 {
		t.Errorf("expected 2 ack results, got %d", len(ackPayload.SyncedPolicies))
	}
}

func TestRunSyncNoPolicies(t *testing.T) {
	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/internal/gateways/gw-test/config" && r.Method == "GET" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(GatewayConfigResponse{
				GatewayID:       "gw-test",
				PendingPolicies: []PendingPolicy{},
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer cpServer.Close()

	agent := New(Config{
		ControlPlaneURL: cpServer.URL,
		GatewayAPIKey:   "key",
	})
	agent.gatewayID = "gw-test"

	adapter := &mockSyncAdapter{}
	agent.RunSync(context.Background(), adapter, cpServer.URL)

	if len(adapter.appliedPolicies) != 0 {
		t.Errorf("expected no applied policies, got %d", len(adapter.appliedPolicies))
	}
}

func TestStartSyncSkipsNoURL(t *testing.T) {
	agent := New(Config{
		ControlPlaneURL: "http://localhost",
		GatewayAPIKey:   "key",
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Should not panic
	agent.StartSync(ctx, &mockSyncAdapter{}, "", SyncConfig{})
}

func TestReportRouteSyncAck(t *testing.T) {
	var receivedPayload RouteSyncAckPayload

	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/internal/gateways/gw-test/route-sync-ack" && r.Method == "POST" {
			if r.Header.Get("X-Gateway-Key") != "key" {
				w.WriteHeader(http.StatusUnauthorized)
				return
			}
			_ = json.NewDecoder(r.Body).Decode(&receivedPayload)
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
	agent.gatewayID = "gw-test"

	results := []SyncedRouteResult{
		{DeploymentID: "dep-1", Status: "applied"},
		{DeploymentID: "dep-2", Status: "failed", Error: "timeout"},
	}

	err := agent.ReportRouteSyncAck(context.Background(), results)
	if err != nil {
		t.Fatalf("report route-sync-ack error: %v", err)
	}
	if len(receivedPayload.SyncedRoutes) != 2 {
		t.Errorf("expected 2 results, got %d", len(receivedPayload.SyncedRoutes))
	}
	if receivedPayload.SyncTimestamp == "" {
		t.Error("expected non-empty sync_timestamp")
	}
	if receivedPayload.SyncedRoutes[0].DeploymentID != "dep-1" {
		t.Errorf("expected dep-1, got %s", receivedPayload.SyncedRoutes[0].DeploymentID)
	}
	if receivedPayload.SyncedRoutes[1].Status != "failed" {
		t.Errorf("expected failed status, got %s", receivedPayload.SyncedRoutes[1].Status)
	}
}

func TestReportRouteSyncAckNotRegistered(t *testing.T) {
	agent := New(Config{
		ControlPlaneURL: "http://localhost",
		GatewayAPIKey:   "key",
	})

	err := agent.ReportRouteSyncAck(context.Background(), []SyncedRouteResult{
		{DeploymentID: "dep-1", Status: "applied"},
	})
	if err == nil {
		t.Fatal("expected error when not registered")
	}
	if err.Error() != "not registered" {
		t.Errorf("expected 'not registered', got %s", err.Error())
	}
}

func TestReportRouteSyncAckServerError(t *testing.T) {
	cpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("internal error"))
	}))
	defer cpServer.Close()

	agent := New(Config{
		ControlPlaneURL: cpServer.URL,
		GatewayAPIKey:   "key",
	})
	agent.gatewayID = "gw-test"

	err := agent.ReportRouteSyncAck(context.Background(), []SyncedRouteResult{
		{DeploymentID: "dep-1", Status: "applied"},
	})
	if err == nil {
		t.Fatal("expected error on server error")
	}
}
