package connect

import (
	"context"
	"log"
	"time"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// runCredentialSyncLoop drives the credential-sync ticker loop. Runs
// a.RunCredentialSync immediately then on each interval tick. Vault token
// renewal is handled inside RunCredentialSync itself (see credentials.go).
func runCredentialSyncLoop(ctx context.Context, a *Agent, vc *VaultClient, adapter adapters.GatewayAdapter, adminURL, tenantID string, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	a.RunCredentialSync(ctx, vc, adapter, adminURL, tenantID)
	for {
		select {
		case <-ctx.Done():
			log.Println("credential-sync stopped")
			return
		case <-ticker.C:
			a.RunCredentialSync(ctx, vc, adapter, adminURL, tenantID)
		}
	}
}
