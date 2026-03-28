package connect

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
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

// FetchRoutes pulls the route table from the CP via GET /v1/internal/gateways/routes.
func (a *Agent) FetchRoutes(ctx context.Context) ([]adapters.Route, error) {
	ctx, span := a.startSpan(ctx, "stoa-connect.routes.fetch",
		attribute.String("stoa.gateway_id", a.gatewayID),
	)
	defer span.End()

	url := fmt.Sprintf("%s/v1/internal/gateways/routes", a.cfg.ControlPlaneURL)
	if a.cfg.InstanceName != "" {
		url += "?gateway_name=" + a.cfg.InstanceName
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "create request failed")
		return nil, fmt.Errorf("create routes request: %w", err)
	}
	req.Header.Set("X-Gateway-Key", a.cfg.GatewayAPIKey)

	resp, err := a.client.Do(req)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "request failed")
		return nil, fmt.Errorf("routes request: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	body, _ := io.ReadAll(resp.Body)
	span.SetAttributes(attribute.Int("http.status_code", resp.StatusCode))

	if resp.StatusCode != http.StatusOK {
		err := fmt.Errorf("routes request failed (%d): %s", resp.StatusCode, string(body))
		span.RecordError(err)
		span.SetStatus(codes.Error, "fetch routes rejected")
		return nil, err
	}

	var routes []adapters.Route
	if err := json.Unmarshal(body, &routes); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "decode failed")
		return nil, fmt.Errorf("decode routes response: %w", err)
	}

	span.SetAttributes(attribute.Int("stoa.routes_count", len(routes)))
	span.SetStatus(codes.Ok, "routes fetched")
	return routes, nil
}

// RunRouteSync performs a single route sync cycle: fetch CP routes → push to local gateway.
func (a *Agent) RunRouteSync(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string) {
	ctx, span := a.startSpan(ctx, "stoa-connect.routes.sync",
		attribute.String("stoa.gateway_id", a.gatewayID),
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

	syncErr := adapter.SyncRoutes(ctx, adminURL, routes)

	// Build ack results based on sync outcome
	var results []SyncedRouteResult
	for _, r := range routes {
		result := SyncedRouteResult{DeploymentID: r.DeploymentID}
		if r.DeploymentID == "" {
			continue // Skip routes without deployment tracking
		}
		if syncErr != nil {
			result.Status = "failed"
			result.Error = syncErr.Error()
		} else {
			result.Status = "applied"
		}
		results = append(results, result)
	}

	// Report route sync results to CP (fire-and-forget: log warning on failure)
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

// StartRouteSync starts a background goroutine that syncs CP routes
// to the local gateway at the configured interval.
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

	ticker := time.NewTicker(interval)
	go func() {
		defer ticker.Stop()
		// Run immediately on start
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
	}()
}
