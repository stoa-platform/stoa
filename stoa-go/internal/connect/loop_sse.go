package connect

import (
	"context"
	"log"
	"time"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// runSSEStream drives the SSE deployment-stream reconnect loop. Before
// each connect attempt it runs a route-sync catch-up to reconcile any
// deployment missed during a disconnection. On terminal error from
// sseStream, it waits according to the backoff policy and reconnects.
//
// Exits cleanly on ctx cancellation.
func runSSEStream(ctx context.Context, a *Agent, adapter adapters.GatewayAdapter, adminURL string, policy backoffPolicy) {
	attempt := 0
	for {
		select {
		case <-ctx.Done():
			log.Println("sse-stream stopped")
			return
		default:
		}

		// Catch up on any missed deployments before streaming.
		a.RunRouteSync(ctx, adapter, adminURL)

		err := a.streamEvents(ctx, adapter, adminURL)
		if err == nil || ctx.Err() != nil {
			// Clean disconnect or context cancelled — reset attempt and loop.
			attempt = 0
			continue
		}

		attempt++
		wait := policy.backoff(attempt)
		log.Printf("sse-stream: terminal error: %v (reconnecting in %s, attempt %d)", err, wait, attempt)
		select {
		case <-ctx.Done():
			return
		case <-time.After(wait):
		}
	}
}
