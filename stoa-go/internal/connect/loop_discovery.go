package connect

import (
	"context"
	"log"
	"time"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// runDiscoveryLoop drives the gateway-discovery ticker loop. Runs
// a.runDiscovery immediately then on each interval tick.
func runDiscoveryLoop(ctx context.Context, a *Agent, adapter adapters.GatewayAdapter, adminURL string, interval time.Duration) {
	a.runDiscovery(ctx, adapter, adminURL)
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			log.Println("discovery stopped")
			return
		case <-ticker.C:
			a.runDiscovery(ctx, adapter, adminURL)
		}
	}
}
