package connect

import (
	"context"
	"log"
	"os"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// CredentialSyncConfig holds configuration for the credential sync loop.
type CredentialSyncConfig struct {
	// Interval between credential sync cycles (default 60s).
	Interval time.Duration
	// TenantID to fetch credentials for.
	TenantID string
}

// CredentialSyncConfigFromEnv creates a CredentialSyncConfig from environment variables.
func CredentialSyncConfigFromEnv() CredentialSyncConfig {
	cfg := CredentialSyncConfig{
		Interval: 60 * time.Second,
		TenantID: os.Getenv("STOA_TENANT_ID"),
	}
	if interval := os.Getenv("STOA_CREDENTIAL_SYNC_INTERVAL"); interval != "" {
		if d, err := time.ParseDuration(interval); err == nil {
			cfg.Interval = d
		}
	}
	return cfg
}

// RunCredentialSync performs a single credential sync cycle:
// read from Vault → inject into local gateway.
func (a *Agent) RunCredentialSync(ctx context.Context, vc *VaultClient, adapter adapters.GatewayAdapter, adminURL string, tenantID string) {
	ctx, span := a.startSpan(ctx, "stoa-connect.credentials.sync",
		attribute.String("stoa.tenant_id", tenantID),
	)
	defer span.End()

	// 1. Check token health and renew if needed
	ttl := vc.TokenTTL(ctx)
	if ttl > 0 && ttl < 300 { // Renew if < 5 min remaining
		if err := vc.RenewToken(ctx); err != nil {
			log.Printf("credential-sync: vault token renewal warning: %v", err)
		}
	}

	// 2. Fetch credentials from Vault
	creds, err := vc.ReadCredentials(ctx, tenantID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "vault read failed")
		log.Printf("credential-sync: vault read error: %v", err)
		return
	}

	if len(creds) == 0 {
		span.SetAttributes(attribute.Int("stoa.credentials_count", 0))
		log.Println("credential-sync: no credentials to sync")
		return
	}

	span.SetAttributes(attribute.Int("stoa.credentials_count", len(creds)))
	log.Printf("credential-sync: %d credentials to inject", len(creds))

	// 3. Inject into local gateway
	if err := adapter.InjectCredentials(ctx, adminURL, creds); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "inject credentials failed")
		log.Printf("credential-sync: inject error: %v", err)
		return
	}

	span.SetStatus(codes.Ok, "credentials synced")
	log.Printf("credential-sync: injected %d credentials", len(creds))
}

// StartCredentialSync starts a background goroutine that syncs credentials
// from Vault to the local gateway at the configured interval. See
// runCredentialSyncLoop in loop_credentials.go for the loop body.
func (a *Agent) StartCredentialSync(ctx context.Context, vc *VaultClient, adapter adapters.GatewayAdapter, adminURL string, cfg CredentialSyncConfig) {
	if adminURL == "" {
		log.Println("credential-sync skipped: no gateway admin URL configured")
		return
	}
	if cfg.TenantID == "" {
		log.Println("credential-sync skipped: STOA_TENANT_ID not set")
		return
	}
	interval := cfg.Interval
	if interval == 0 {
		interval = 60 * time.Second
	}
	log.Printf("starting credential sync loop (interval=%s, tenant=%s)", interval, cfg.TenantID)
	go runCredentialSyncLoop(ctx, a, vc, adapter, adminURL, cfg.TenantID, interval)
}
