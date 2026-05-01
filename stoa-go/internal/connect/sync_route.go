package connect

import (
	"context"
	"log"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// routeSyncer pushes a batch of routes to the local gateway adapter and
// produces per-route SyncStep-annotated results ready for CP route-sync-ack.
//
// It is the SINGLE code path used by both:
//   - RunRouteSync (polling, N routes per cycle)
//   - handleSyncDeployment (SSE, 1 route per deployment event)
//
// Previously these two paths duplicated step construction, per-route status
// resolution and result assembly — and had diverged. See REWRITE-BUGS.md
// B.1..B.3 for the divergences consolidated here; most notably the
// Generation field (CAB-1950) is now always propagated.
//
// routeSyncer is stateless; the caller decides whether to re-use the
// instance per call or per agent. Cost-wise the difference is negligible.
type routeSyncer struct {
	adapter adapters.GatewayAdapter
}

func newRouteSyncer(adapter adapters.GatewayAdapter) *routeSyncer {
	return &routeSyncer{adapter: adapter}
}

// Sync pushes routes to the adapter at adminURL and returns one
// SyncedRouteResult per route that carries a DeploymentID. The second
// return is the adapter's global error (if any) for callers that want to
// log it alongside the per-route results.
//
// Behavior:
//   - Empty routes → returns nil, nil (caller decides what to log).
//   - Route without DeploymentID → logged as warning, skipped in results.
//     Symptom of a CP↔agent contract drift (CP should always tag routes
//     with deployment_id).
//   - Steps attached to each result: agent_received, adapter_connected,
//     api_synced (with the adapter's actual outcome + error detail).
//   - Per-route status resolution priority:
//     1. adapter reported the route in SyncResult.FailedRoutes →
//     status=failed with the adapter's own error string.
//     2. adapter returned a global error AND no per-route entry → all
//     remaining routes get status=failed with the global error
//     (fallback for adapters like kong/gravitee that don't track per-route).
//     3. otherwise → status=applied.
func (s *routeSyncer) Sync(ctx context.Context, adminURL string, routes []adapters.Route) ([]SyncedRouteResult, error) {
	if len(routes) == 0 {
		return nil, nil
	}

	// Step trace: agent_received and adapter_connected are success by the
	// time we call the adapter. api_synced reflects the adapter's actual
	// outcome. All routes in a single call share the same step timeline.
	agentStep := newSyncStep("agent_received", "success", "")
	adapterStep := newSyncStep("adapter_connected", "success", "")

	syncOutcome, syncErr := s.adapter.SyncRoutes(ctx, adminURL, routes)

	failedMap := syncOutcome.FailedRoutes

	var results []SyncedRouteResult
	for _, r := range routes {
		if r.DeploymentID == "" {
			log.Printf("route-sync: skipping route %q — missing deployment_id (CP contract drift?)", r.Name)
			continue
		}
		apiStep := newSyncStep("api_synced", "success", "")
		result := SyncedRouteResult{
			DeploymentID: r.DeploymentID,
			Generation:   r.Generation, // CAB-1950 — propagated on both paths (B.1 fix)
		}
		if routeErr, failed := failedMap[r.DeploymentID]; failed {
			result.Status = "failed"
			result.Error = routeErr
			apiStep = newSyncStep("api_synced", "failed", routeErr)
		} else if syncErr != nil && len(failedMap) == 0 {
			result.Status = "failed"
			result.Error = syncErr.Error()
			apiStep = newSyncStep("api_synced", "failed", syncErr.Error())
		} else {
			result.Status = "applied"
		}
		result.Steps = []SyncStep{agentStep, adapterStep, apiStep}
		results = append(results, result)
	}

	return results, syncErr
}
