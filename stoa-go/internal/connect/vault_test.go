package connect

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestVaultConfigFromEnv(t *testing.T) {
	cfg := VaultConfigFromEnv()
	if cfg.Path != "stoa" {
		t.Errorf("expected default path 'stoa', got %s", cfg.Path)
	}

	t.Setenv("VAULT_ADDR", "http://vault:8200")
	t.Setenv("VAULT_KV_PATH", "secret")
	cfg = VaultConfigFromEnv()
	if cfg.Addr != "http://vault:8200" {
		t.Errorf("expected addr http://vault:8200, got %s", cfg.Addr)
	}
	if cfg.Path != "secret" {
		t.Errorf("expected path 'secret', got %s", cfg.Path)
	}
}

func TestNewVaultClientNoAddr(t *testing.T) {
	_, err := NewVaultClient(VaultConfig{})
	if err == nil {
		t.Fatal("expected error when no VAULT_ADDR")
	}
}

func TestNewVaultClientNoAuth(t *testing.T) {
	_, err := NewVaultClient(VaultConfig{Addr: "http://vault:8200"})
	if err == nil {
		t.Fatal("expected error when no auth configured")
	}
}

func TestNewVaultClientWithToken(t *testing.T) {
	vc, err := NewVaultClient(VaultConfig{
		Addr:  "http://vault:8200",
		Token: "test-token",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if vc == nil {
		t.Fatal("expected non-nil client")
	}
}

func TestReadCredentials(t *testing.T) {
	vaultServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/stoa/data/consumers/tenant-a" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"data": map[string]interface{}{
					"data": map[string]interface{}{
						"credentials": []interface{}{
							map[string]interface{}{
								"consumer_id": "consumer-1",
								"api_name":    "petstore",
								"auth_type":   "key-auth",
								"key":         "api-key-123",
							},
							map[string]interface{}{
								"consumer_id": "consumer-2",
								"api_name":    "users",
								"auth_type":   "basic-auth",
								"key":         "admin",
								"secret":      "password123",
							},
						},
					},
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

	creds, err := vc.ReadCredentials(context.Background(), "tenant-a")
	if err != nil {
		t.Fatalf("read credentials: %v", err)
	}
	if len(creds) != 2 {
		t.Fatalf("expected 2 credentials, got %d", len(creds))
	}
	if creds[0].ConsumerID != "consumer-1" {
		t.Errorf("expected consumer-1, got %s", creds[0].ConsumerID)
	}
	if creds[0].AuthType != "key-auth" {
		t.Errorf("expected key-auth, got %s", creds[0].AuthType)
	}
	if creds[1].Secret != "password123" {
		t.Errorf("expected password123, got %s", creds[1].Secret)
	}
}

func TestReadCredentialsNoData(t *testing.T) {
	vaultServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
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

	creds, err := vc.ReadCredentials(context.Background(), "nonexistent")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(creds) != 0 {
		t.Errorf("expected 0 credentials, got %d", len(creds))
	}
}
