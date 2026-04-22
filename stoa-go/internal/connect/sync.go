package connect

import (
	"context"
	"log"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// SyncConfig holds configuration for the policy sync loop.
type SyncConfig struct {
	// Interval between sync cycles (default 60s).
	Interval time.Duration
}

// FetchConfig pulls the gateway config (policies, deployments) from the CP.
// Thin delegator — HTTP logic lives in cpClient.FetchConfig.
func (a *Agent) FetchConfig(ctx context.Context) (*GatewayConfigResponse, error) {
	gatewayID := a.state.GatewayID()
	if gatewayID == "" {
		return nil, ErrNotRegistered
	}
	return a.cp.FetchConfig(ctx, gatewayID)
}

// ReportSyncAck sends policy sync results to the CP.
func (a *Agent) ReportSyncAck(ctx context.Context, results []SyncedPolicyResult) error {
	gatewayID := a.state.GatewayID()
	if gatewayID == "" {
		return ErrNotRegistered
	}
	return a.cp.ReportSyncAck(ctx, gatewayID, SyncAckPayload{
		SyncedPolicies: results,
		SyncTimestamp:  time.Now().UTC().Format(time.RFC3339),
	})
}

// ReportRouteSyncAck sends route sync results to the CP.
func (a *Agent) ReportRouteSyncAck(ctx context.Context, results []SyncedRouteResult) error {
	gatewayID := a.state.GatewayID()
	if gatewayID == "" {
		return ErrNotRegistered
	}
	return a.cp.ReportRouteSyncAck(ctx, gatewayID, RouteSyncAckPayload{
		SyncedRoutes:  results,
		SyncTimestamp: time.Now().UTC().Format(time.RFC3339),
	})
}

// RunSync performs a single policy sync cycle: fetch config → dispatch via
// policySyncer → update metrics → ack. Per-policy dispatch (OIDC vs
// generic, apply vs remove) lives in sync_policy.go.
func (a *Agent) RunSync(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string) {
	ctx, span := a.startSpan(ctx, "stoa-connect.sync",
		attribute.String("stoa.gateway_id", a.state.GatewayID()),
	)
	defer span.End()

	config, err := a.FetchConfig(ctx)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "fetch config failed")
		log.Printf("sync: fetch config error: %v", err)
		return
	}

	if len(config.PendingPolicies) == 0 {
		span.SetAttributes(attribute.Int("stoa.pending_policies", 0))
		log.Println("sync: no pending policies")
		return
	}

	span.SetAttributes(attribute.Int("stoa.pending_policies", len(config.PendingPolicies)))
	log.Printf("sync: %d policies to reconcile", len(config.PendingPolicies))

	syncer := newPolicySyncer(adapter)
	results := syncer.SyncPolicies(ctx, adminURL, config.PendingPolicies)

	// Update Prometheus metrics
	allOk := true
	for _, r := range results {
		switch r.Status {
		case "applied", "removed":
			SyncPoliciesApplied.Inc()
		case "failed":
			SyncPoliciesFailed.Inc()
			allOk = false
		}
	}
	if allOk {
		SyncStatus.Set(1)
	} else {
		SyncStatus.Set(0)
	}

	// Report sync results to CP
	if err := a.ReportSyncAck(ctx, results); err != nil {
		span.RecordError(err)
		log.Printf("sync: report ack error: %v", err)
	}

	span.SetStatus(codes.Ok, "sync cycle complete")
}

// StartSync starts a background goroutine that syncs policies at the configured interval.
func (a *Agent) StartSync(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string, cfg SyncConfig) {
	if adminURL == "" {
		log.Println("sync skipped: no gateway admin URL configured")
		return
	}

	interval := cfg.Interval
	if interval == 0 {
		interval = 60 * time.Second
	}

	log.Printf("starting policy sync loop (interval=%s)", interval)

	ticker := time.NewTicker(interval)
	go func() {
		defer ticker.Stop()
		// Run immediately on start
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
	}()
}
