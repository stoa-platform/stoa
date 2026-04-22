package connect

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// SSEConfig holds configuration for the SSE deployment stream (ADR-059).
type SSEConfig struct {
	// Enabled toggles SSE mode (replaces route polling when true).
	Enabled bool
	// ReconnectInterval is the delay before reconnecting after a stream drop.
	ReconnectInterval time.Duration
	// MaxReconnectInterval caps exponential backoff.
	MaxReconnectInterval time.Duration
}

// SSEConfigFromEnv creates an SSEConfig from environment variables.
func SSEConfigFromEnv() SSEConfig {
	cfg := SSEConfig{
		Enabled:              os.Getenv("STOA_SSE_ENABLED") == "true",
		ReconnectInterval:    2 * time.Second,
		MaxReconnectInterval: 60 * time.Second,
	}
	if d := os.Getenv("STOA_SSE_RECONNECT_INTERVAL"); d != "" {
		if parsed, err := time.ParseDuration(d); err == nil {
			cfg.ReconnectInterval = parsed
		}
	}
	return cfg
}

// StartDeploymentStream starts an SSE listener for real-time deployment events (ADR-059).
// On each event, it syncs the route to the local gateway and reports back via route-sync-ack.
// On disconnect, it catches up via RunRouteSync() then resumes SSE with exponential backoff.
func (a *Agent) StartDeploymentStream(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string, cfg SSEConfig) {
	if a.state.GatewayID() == "" {
		log.Println("sse-stream skipped: not registered with CP")
		return
	}
	if adminURL == "" {
		log.Println("sse-stream skipped: no gateway admin URL configured")
		return
	}

	policy := backoffPolicy{
		Initial:    cfg.ReconnectInterval,
		Max:        cfg.MaxReconnectInterval,
		Multiplier: 2.0,
	}
	log.Printf("starting SSE deployment stream (initial=%s max=%s)", policy.Initial, policy.Max)

	go func() {
		attempt := 0

		for {
			select {
			case <-ctx.Done():
				log.Println("sse-stream stopped")
				return
			default:
			}

			// Catch up on any missed deployments before streaming
			a.RunRouteSync(ctx, adapter, adminURL)

			err := a.streamEvents(ctx, adapter, adminURL)
			if err != nil && ctx.Err() == nil {
				attempt++
				wait := policy.backoff(attempt)
				log.Printf("sse-stream: terminal error: %v (reconnecting in %s, attempt %d)", err, wait, attempt)
				select {
				case <-ctx.Done():
					return
				case <-time.After(wait):
				}
			} else {
				// Reset attempt counter on clean disconnect
				attempt = 0
			}
		}
	}()
}

// streamEvents connects to the SSE endpoint via a.sse and dispatches each
// parsed rawEvent through a per-call dispatcher wired with the adapter +
// adminURL closures. Returns the terminal cause surfaced by sseStream.Run.
//
// A fresh dispatcher is built per call (cheap — handlers are closure refs)
// so reconnects pick up the latest adapter/adminURL if the caller ever
// re-invokes with different values. In practice the args are stable across
// the lifetime of StartDeploymentStream.
func (a *Agent) streamEvents(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string) error {
	dispatcher := a.newSSEDispatcher(adapter, adminURL)
	gatewayID := a.state.GatewayID()
	return a.sse.Run(ctx, gatewayID, func(evCtx context.Context, ev rawEvent) error {
		dispatcher.Dispatch(evCtx, ev)
		return nil
	})
}

// newSSEDispatcher wires the SSE event table. sync-deployment applies the
// route to the local gateway via handleSyncDeployment; heartbeat is an
// explicit no-op so the unknown-event log line stays silent on every
// keepalive. Unknown types are logged by the dispatcher itself.
func (a *Agent) newSSEDispatcher(adapter adapters.GatewayAdapter, adminURL string) *eventDispatcher {
	d := newEventDispatcher()
	d.Register("sync-deployment", func(ctx context.Context, data []byte) {
		a.handleSyncDeployment(ctx, adapter, adminURL, data)
	})
	d.Register("heartbeat", func(ctx context.Context, data []byte) {
		// keepalive — deliberately empty
	})
	return d
}

// handleSyncDeployment processes a sync-deployment SSE event: decode the
// event wrapper + desired_state, route the single-route batch through the
// unified routeSyncer, and ack the result. Shares the route-sync code
// path with the polling loop (RunRouteSync) — see sync_route.go.
func (a *Agent) handleSyncDeployment(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string, data []byte) {
	ctx, span := a.startSpan(ctx, "stoa-connect.sse.sync-deployment",
		attribute.String("stoa.gateway_id", a.state.GatewayID()),
	)
	defer span.End()

	var event DeploymentEvent
	if err := json.Unmarshal(data, &event); err != nil {
		// No deployment_id known — cannot ack. Surface + drop.
		log.Printf("sse-stream: decode deployment event error: %v", err)
		span.RecordError(err)
		return
	}

	span.SetAttributes(attribute.String("stoa.deployment_id", event.DeploymentID))
	log.Printf("sse-stream: received deployment %s (status=%s)", event.DeploymentID, event.SyncStatus)

	var route adapters.Route
	if err := json.Unmarshal(event.DesiredState, &route); err != nil {
		// Synthesize a failed ack with the same 3-step shape the polling
		// path produces, so CP UI renders a consistent step trace. Note:
		// Generation is unknown at this point (desired_state undecodable).
		decodeDetail := fmt.Sprintf("decode desired_state: %v", err)
		log.Printf("sse-stream: %s", decodeDetail)
		span.RecordError(err)
		span.SetStatus(codes.Error, "decode desired_state failed")
		a.ackRouteResult(ctx, SyncedRouteResult{
			DeploymentID: event.DeploymentID,
			Status:       "failed",
			Error:        decodeDetail,
			Steps: []SyncStep{
				newSyncStep("agent_received", "success", ""),
				newSyncStep("adapter_connected", "success", ""),
				newSyncStep("api_synced", "failed", decodeDetail),
			},
		})
		return
	}
	route.DeploymentID = event.DeploymentID

	syncer := newRouteSyncer(adapter)
	results, syncErr := syncer.Sync(ctx, adminURL, []adapters.Route{route})

	if syncErr != nil {
		span.RecordError(syncErr)
		span.SetStatus(codes.Error, "sync failed")
		log.Printf("sse-stream: sync deployment %s failed: %v", event.DeploymentID, syncErr)
	} else {
		span.SetStatus(codes.Ok, "synced")
		log.Printf("sse-stream: sync deployment %s applied", event.DeploymentID)
	}

	for _, result := range results {
		a.ackRouteResult(ctx, result)
	}
}

// ackRouteResult sends a single SyncedRouteResult via route-sync-ack,
// logging on failure (fire-and-forget: the next sync cycle re-reconciles).
func (a *Agent) ackRouteResult(ctx context.Context, result SyncedRouteResult) {
	if err := a.ReportRouteSyncAck(ctx, []SyncedRouteResult{result}); err != nil {
		log.Printf("sse-stream: ack error for %s: %v", result.DeploymentID, err)
	}
}
