package connect

import (
	"context"
	"log"
	"time"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// runPolicySync drives the policy-sync ticker loop. Runs RunSync immediately
// then on each interval tick until ctx is cancelled.
func runPolicySync(ctx context.Context, a *Agent, adapter adapters.GatewayAdapter, adminURL string, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	a.RunSync(ctx, adapter, adminURL)
	for {
		select {
		case <-ctx.Done():
			log.Println("sync stopped")
			return
		case <-ticker.C:
			a.RunSync(ctx, adapter, adminURL)
		}
	}
}

// runRouteSyncPolling drives the route-sync polling ticker loop (fallback
// when SSE is disabled). Runs RunRouteSync immediately then on each tick.
func runRouteSyncPolling(ctx context.Context, a *Agent, adapter adapters.GatewayAdapter, adminURL string, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	a.RunRouteSync(ctx, adapter, adminURL)
	for {
		select {
		case <-ctx.Done():
			log.Println("route-sync stopped")
			return
		case <-ticker.C:
			a.RunRouteSync(ctx, adapter, adminURL)
		}
	}
}
