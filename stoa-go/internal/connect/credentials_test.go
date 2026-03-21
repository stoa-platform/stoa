package connect

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

func TestRunCredentialSyncInjectsCredentials(t *testing.T) {
	vaultServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/stoa/data/consumers/tenant-a" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"data": map[string]interface{}{
					"data": map[string]interface{}{
						"credentials": []interface{}{
							map[string]interface{}{
								"consumer_id": "c1",
								"api_name":    "api-a",
								"auth_type":   "key-auth",
								"key":         "key-123",
							},
						},
					},
				},
			})
			return
		}
		// Token lookup for TTL check
		if r.URL.Path == "/v1/auth/token/lookup-self" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"data": map[string]interface{}{
					"ttl": float64(3600),
				},
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer vaultServer.Close()

	vc, err := NewVaultClient(VaultConfig{
		Addr:  vaultServer.URL,
		Token: "test-token",
		Path:  "stoa",
	})
	if err != nil {
		t.Fatalf("create vault client: %v", err)
	}

	agent := New(Config{
		ControlPlaneURL: "http://localhost",
		GatewayAPIKey:   "key",
	})

	adapter := &mockSyncAdapter{}
	agent.RunCredentialSync(context.Background(), vc, adapter, "http://gateway:8001", "tenant-a")

	if len(adapter.injectedCreds) != 1 {
		t.Fatalf("expected 1 injected credential, got %d", len(adapter.injectedCreds))
	}
	if adapter.injectedCreds[0].Key != "key-123" {
		t.Errorf("expected key-123, got %s", adapter.injectedCreds[0].Key)
	}
}

func TestRunCredentialSyncNoCredentials(t *testing.T) {
	vaultServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/auth/token/lookup-self" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"data": map[string]interface{}{"ttl": float64(3600)},
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer vaultServer.Close()

	vc, err := NewVaultClient(VaultConfig{
		Addr:  vaultServer.URL,
		Token: "test-token",
	})
	if err != nil {
		t.Fatalf("create vault client: %v", err)
	}

	agent := New(Config{
		ControlPlaneURL: "http://localhost",
		GatewayAPIKey:   "key",
	})

	adapter := &mockSyncAdapter{}
	agent.RunCredentialSync(context.Background(), vc, adapter, "http://gateway:8001", "nonexistent")

	if len(adapter.injectedCreds) != 0 {
		t.Errorf("expected 0 injected credentials, got %d", len(adapter.injectedCreds))
	}
}

func TestStartCredentialSyncSkipsNoURL(t *testing.T) {
	agent := New(Config{
		ControlPlaneURL: "http://localhost",
		GatewayAPIKey:   "key",
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Should not panic
	agent.StartCredentialSync(ctx, nil, &mockSyncAdapter{}, "", CredentialSyncConfig{TenantID: "t1"})
}

func TestStartCredentialSyncSkipsNoTenant(t *testing.T) {
	agent := New(Config{
		ControlPlaneURL: "http://localhost",
		GatewayAPIKey:   "key",
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Should not panic
	agent.StartCredentialSync(ctx, nil, &mockSyncAdapter{}, "http://gw:8001", CredentialSyncConfig{})
}

func TestCredentialSyncConfigFromEnv(t *testing.T) {
	cfg := CredentialSyncConfigFromEnv()
	if cfg.Interval != 60*1e9 {
		t.Errorf("expected default 60s interval, got %s", cfg.Interval)
	}

	t.Setenv("STOA_CREDENTIAL_SYNC_INTERVAL", "30s")
	t.Setenv("STOA_TENANT_ID", "acme")
	cfg = CredentialSyncConfigFromEnv()
	if cfg.Interval != 30*1e9 {
		t.Errorf("expected 30s interval, got %s", cfg.Interval)
	}
	if cfg.TenantID != "acme" {
		t.Errorf("expected tenant acme, got %s", cfg.TenantID)
	}
}

func TestKongInjectCredentials(t *testing.T) {
	var createdConsumer bool
	var createdCred bool

	gwServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/consumers/stoa-c1" && r.Method == "PUT":
			createdConsumer = true
			w.WriteHeader(http.StatusOK)
		case r.URL.Path == "/consumers/stoa-c1/key-auth" && r.Method == "POST":
			createdCred = true
			w.WriteHeader(http.StatusCreated)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer gwServer.Close()

	adapter := adapters.NewKongAdapter(adapters.AdapterConfig{})
	creds := []adapters.Credential{
		{ConsumerID: "c1", APIName: "api-a", AuthType: "key-auth", Key: "my-key"},
	}

	err := adapter.InjectCredentials(context.Background(), gwServer.URL, creds)
	if err != nil {
		t.Fatalf("inject credentials error: %v", err)
	}
	if !createdConsumer {
		t.Error("expected consumer creation")
	}
	if !createdCred {
		t.Error("expected credential creation")
	}
}
