package adapters

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/stoa-platform/stoa-go/internal/xds"
)

// UnsupportedError reports operations Envoy cannot perform. No changes are made.
type UnsupportedError struct{ Operation string }

func (e *UnsupportedError) Error() string { return "envoy: unsupported operation: " + e.Operation }

// EnvoyControlPlane publishes snapshots and waits for their acknowledgement.
type EnvoyControlPlane interface {
	Update(context.Context, []xds.Route) (string, error)
	WaitAck(context.Context, string, time.Duration) error
}

// EnvoyAdapter synchronizes routes and supported policies. Discovery and
// credential injection fail explicitly; unsupported policies are never ignored.
type EnvoyAdapter struct {
	Server      EnvoyControlPlane
	mu          sync.Mutex
	routes      []Route // last fully acknowledged table
	generations map[string]int
	policies    map[string]PolicyAction
}

func NewEnvoyAdapter(server EnvoyControlPlane) *EnvoyAdapter { return &EnvoyAdapter{Server: server} }
func (*EnvoyAdapter) Detect(context.Context, string) (bool, error) {
	return false, &UnsupportedError{"Detect"}
}
func (*EnvoyAdapter) Discover(context.Context, string) ([]DiscoveredAPI, error) {
	return nil, &UnsupportedError{"Discover"}
}
func (*EnvoyAdapter) InjectCredentials(context.Context, string, []Credential) error {
	return &UnsupportedError{"InjectCredentials"}
}

func (a *EnvoyAdapter) SyncRoutes(ctx context.Context, _ string, routes []Route) (SyncResult, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	for _, r := range routes {
		if r.Generation > 0 && r.Generation < a.generations[r.DeploymentID] {
			return SyncResult{FailedRoutes: map[string]string{}}, fmt.Errorf("envoy: refusing stale route table")
		}
	}
	for _, old := range a.routes {
		found := false
		for _, r := range routes {
			if r.DeploymentID == old.DeploymentID && r.ID == old.ID && r.APICatalogID == old.APICatalogID && (r.Activated || r.Removing) {
				found = true
				break
			}
		}
		if !found {
			return SyncResult{FailedRoutes: map[string]string{}}, fmt.Errorf("envoy: refusing route loss without an explicit tombstone")
		}
	}
	return a.syncRoutes(ctx, routes)
}

// SyncRouteEvent merges one targeted SSE change into the last complete table.
// Only explicit tombstones authorize removal, including the final route.
func (a *EnvoyAdapter) SyncRouteEvent(ctx context.Context, route Route) (SyncResult, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if route.DeploymentID == "" {
		return SyncResult{FailedRoutes: map[string]string{}}, fmt.Errorf("envoy: deployment identity required")
	}
	if route.Generation > 0 && route.Generation <= a.generations[route.DeploymentID] {
		return SyncResult{FailedRoutes: map[string]string{}}, nil
	}
	if !route.Activated && !route.Removing {
		return SyncResult{FailedRoutes: map[string]string{}}, fmt.Errorf("envoy: refusing route loss without an explicit tombstone")
	}
	routes := make([]Route, 0, len(a.routes)+1)
	for _, old := range a.routes {
		if old.DeploymentID != route.DeploymentID {
			routes = append(routes, old)
		}
	}
	routes = append(routes, route)
	return a.syncRoutes(ctx, routes)
}

func (a *EnvoyAdapter) syncRoutes(ctx context.Context, routes []Route) (SyncResult, error) {
	result := SyncResult{FailedRoutes: map[string]string{}}
	converted := make([]xds.Route, 0, len(routes))
	var err error
	for _, r := range routes {
		if !r.Activated {
			continue
		}
		path := r.PathPrefix
		if path == "" {
			if r.APIID == "" {
				err = fmt.Errorf("envoy: api_id required without path_prefix")
				break
			}
			path = "/apis/" + r.APIID
		}
		id := r.ID
		if id == "" {
			id = r.APICatalogID
		}
		converted = append(converted, xds.Route{TenantID: r.TenantID, APIID: r.APICatalogID, ID: id, Path: path, Backend: r.BackendURL, Methods: append([]string(nil), r.Methods...)})
		converted[len(converted)-1].Policies = a.policiesForRoute(r)
		if _, err = xds.PolicyConfigs(converted[len(converted)-1].Policies); err != nil {
			err = &PolicyError{Code: "invalid"}
			break
		}
	}
	if err == nil {
		if a.Server == nil {
			err = fmt.Errorf("envoy: ADS server is not configured")
		} else {
			var version string
			version, err = a.Server.Update(ctx, converted)
			if err == nil {
				err = a.Server.WaitAck(ctx, version, 0)
			}
		}
	}
	if err != nil {
		for _, r := range routes {
			if (r.Activated || r.Removing) && r.DeploymentID != "" {
				result.FailedRoutes[r.DeploymentID] = err.Error()
			}
		}
	} else {
		if a.generations == nil {
			a.generations = map[string]int{}
		}
		a.routes = nil
		for _, r := range routes {
			a.generations[r.DeploymentID] = r.Generation
			if r.Activated {
				a.routes = append(a.routes, r)
			}
		}
	}
	return result, err
}
