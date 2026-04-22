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

// RouteSyncConfig holds configuration for the route sync loop.
type RouteSyncConfig struct {
	// Interval between route sync cycles (default 30s).
	Interval time.Duration
}

// RouteSyncConfigFromEnv creates a RouteSyncConfig from environment variables.
func RouteSyncConfigFromEnv() RouteSyncConfig {
	cfg := RouteSyncConfig{
		Interval: 30 * time.Second,
	}
	if interval := os.Getenv("STOA_ROUTE_SYNC_INTERVAL"); interval != "" {
		if d, err := time.ParseDuration(interval); err == nil {
			cfg.Interval = d
		}
	}
	return cfg
}

// FetchRoutes pulls the route table from the CP, filtered by InstanceName
// (empty = all). Thin delegator — HTTP logic lives in cpClient.FetchRoutes.
func (a *Agent) FetchRoutes(ctx context.Context) ([]adapters.Route, error) {
	return a.cp.FetchRoutes(ctx, a.cfg.InstanceName)
}

// RunRouteSync performs a single route sync cycle: fetch CP routes → push
// to local gateway via the unified routeSyncer → ack per-route results.
// Shares the route-sync code path with the SSE deployment stream
// (handleSyncDeployment) — see sync_route.go.
func (a *Agent) RunRouteSync(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string) {
	ctx, span := a.startSpan(ctx, "stoa-connect.routes.sync",
		attribute.String("stoa.gateway_id", a.state.GatewayID()),
	)
	defer span.End()

	routes, err := a.FetchRoutes(ctx)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "fetch routes failed")
		log.Printf("route-sync: fetch error: %v", err)
		return
	}

	if len(routes) == 0 {
		span.SetAttributes(attribute.Int("stoa.routes_count", 0))
		log.Println("route-sync: no routes to sync")
		return
	}

	span.SetAttributes(attribute.Int("stoa.routes_count", len(routes)))
	log.Printf("route-sync: %d routes to push", len(routes))

	syncer := newRouteSyncer(adapter)
	results, syncErr := syncer.Sync(ctx, adminURL, routes)

	if len(results) > 0 {
		if ackErr := a.ReportRouteSyncAck(ctx, results); ackErr != nil {
			log.Printf("route-sync: report ack error: %v", ackErr)
		} else {
			log.Printf("route-sync: reported %d ack results to CP", len(results))
		}
	}

	if syncErr != nil {
		span.RecordError(syncErr)
		span.SetStatus(codes.Error, "sync routes failed")
		log.Printf("route-sync: push error: %v", syncErr)
		return
	}

	span.SetStatus(codes.Ok, "routes synced")
	log.Printf("route-sync: pushed %d routes to gateway", len(routes))
}

// StartRouteSync starts a background goroutine that polls CP routes and
// pushes them to the local gateway at the configured interval. Used as the
// fallback when SSE is disabled — see runRouteSyncPolling in loop_sync.go.
func (a *Agent) StartRouteSync(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string, cfg RouteSyncConfig) {
	if adminURL == "" {
		log.Println("route-sync skipped: no gateway admin URL configured")
		return
	}
	interval := cfg.Interval
	if interval == 0 {
		interval = 30 * time.Second
	}
	log.Printf("starting route sync loop (interval=%s)", interval)
	go runRouteSyncPolling(ctx, a, adapter, adminURL, interval)
}
