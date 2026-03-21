package connect

import (
	"context"
	"fmt"
	"log"
	"os"

	vault "github.com/hashicorp/vault/api"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// VaultConfig holds configuration for the Vault client.
type VaultConfig struct {
	Addr     string // VAULT_ADDR
	RoleID   string // VAULT_ROLE_ID (AppRole)
	SecretID string // VAULT_SECRET_ID (AppRole)
	Token    string // VAULT_TOKEN (alternative to AppRole)
	Path     string // KV v2 mount path (default: "stoa")
}

// VaultConfigFromEnv creates a VaultConfig from environment variables.
func VaultConfigFromEnv() VaultConfig {
	cfg := VaultConfig{
		Addr:     os.Getenv("VAULT_ADDR"),
		RoleID:   os.Getenv("VAULT_ROLE_ID"),
		SecretID: os.Getenv("VAULT_SECRET_ID"),
		Token:    os.Getenv("VAULT_TOKEN"),
		Path:     os.Getenv("VAULT_KV_PATH"),
	}
	if cfg.Path == "" {
		cfg.Path = "stoa"
	}
	return cfg
}

// VaultClient wraps the HashiCorp Vault API client for credential reads.
type VaultClient struct {
	client *vault.Client
	cfg    VaultConfig
}

// NewVaultClient creates a new Vault client with AppRole or token auth.
func NewVaultClient(cfg VaultConfig) (*VaultClient, error) {
	if cfg.Addr == "" {
		return nil, fmt.Errorf("VAULT_ADDR is required")
	}

	vaultCfg := vault.DefaultConfig()
	vaultCfg.Address = cfg.Addr

	client, err := vault.NewClient(vaultCfg)
	if err != nil {
		return nil, fmt.Errorf("create vault client: %w", err)
	}

	vc := &VaultClient{client: client, cfg: cfg}

	// Authenticate
	if cfg.Token != "" {
		client.SetToken(cfg.Token)
	} else if cfg.RoleID != "" && cfg.SecretID != "" {
		if err := vc.loginAppRole(); err != nil {
			return nil, fmt.Errorf("vault approle login: %w", err)
		}
	} else {
		return nil, fmt.Errorf("VAULT_TOKEN or VAULT_ROLE_ID+VAULT_SECRET_ID required")
	}

	return vc, nil
}

// loginAppRole authenticates with Vault using AppRole.
func (vc *VaultClient) loginAppRole() error {
	data := map[string]interface{}{
		"role_id":   vc.cfg.RoleID,
		"secret_id": vc.cfg.SecretID,
	}

	resp, err := vc.client.Logical().Write("auth/approle/login", data)
	if err != nil {
		return fmt.Errorf("approle login: %w", err)
	}
	if resp == nil || resp.Auth == nil {
		return fmt.Errorf("approle login: empty response")
	}

	vc.client.SetToken(resp.Auth.ClientToken)
	log.Printf("vault: authenticated via AppRole (lease=%ds)", resp.Auth.LeaseDuration)
	return nil
}

// ReadCredentials reads consumer credentials from Vault KV v2 at the given path.
// Path format: {mount}/data/consumers/{tenant_id}
// Returns a list of Credential structs parsed from the KV secret data.
func (vc *VaultClient) ReadCredentials(ctx context.Context, tenantID string) ([]adapters.Credential, error) {
	path := fmt.Sprintf("%s/data/consumers/%s", vc.cfg.Path, tenantID)

	secret, err := vc.client.Logical().ReadWithContext(ctx, path)
	if err != nil {
		return nil, fmt.Errorf("vault read %s: %w", path, err)
	}
	if secret == nil || secret.Data == nil {
		return nil, nil // No credentials stored
	}

	// KV v2 wraps data in a "data" key
	data, ok := secret.Data["data"].(map[string]interface{})
	if !ok {
		return nil, fmt.Errorf("vault: unexpected data format at %s", path)
	}

	// Parse credentials array from "credentials" key
	credsRaw, ok := data["credentials"].([]interface{})
	if !ok {
		return nil, nil // No credentials key
	}

	var creds []adapters.Credential
	for _, raw := range credsRaw {
		credMap, ok := raw.(map[string]interface{})
		if !ok {
			continue
		}
		cred := adapters.Credential{
			ConsumerID: getString(credMap, "consumer_id"),
			APIName:    getString(credMap, "api_name"),
			AuthType:   getString(credMap, "auth_type"),
			Key:        getString(credMap, "key"),
			Secret:     getString(credMap, "secret"),
		}
		if cred.ConsumerID != "" && cred.Key != "" {
			creds = append(creds, cred)
		}
	}

	return creds, nil
}

// TokenTTL returns the remaining TTL of the current token in seconds.
// Returns 0 if the token lookup fails (e.g., expired).
func (vc *VaultClient) TokenTTL(ctx context.Context) int {
	secret, err := vc.client.Auth().Token().LookupSelfWithContext(ctx)
	if err != nil {
		return 0
	}
	if secret == nil || secret.Data == nil {
		return 0
	}
	ttl, ok := secret.Data["ttl"]
	if !ok {
		return 0
	}
	// Vault returns ttl as json.Number
	switch v := ttl.(type) {
	case float64:
		return int(v)
	case int:
		return v
	}
	return 0
}

// RenewToken attempts to renew the current Vault token.
func (vc *VaultClient) RenewToken(ctx context.Context) error {
	_, err := vc.client.Auth().Token().RenewSelfWithContext(ctx, 0)
	if err != nil {
		// If renewal fails, try re-login with AppRole
		if vc.cfg.RoleID != "" {
			log.Println("vault: token renewal failed, re-authenticating via AppRole")
			return vc.loginAppRole()
		}
		return fmt.Errorf("vault token renewal: %w", err)
	}
	return nil
}

func getString(m map[string]interface{}, key string) string {
	v, _ := m[key].(string)
	return v
}
