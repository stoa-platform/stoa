package adapters

import (
	"context"
	"fmt"
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

// EnvoyAdapter supports route synchronization only. Discovery, policies and
// credential injection fail explicitly; unsupported policies are never ignored.
type EnvoyAdapter struct{ Server EnvoyControlPlane }

func NewEnvoyAdapter(server EnvoyControlPlane) *EnvoyAdapter { return &EnvoyAdapter{Server: server} }
func (*EnvoyAdapter) Detect(context.Context, string) (bool, error) {
	return false, &UnsupportedError{"Detect"}
}
func (*EnvoyAdapter) Discover(context.Context, string) ([]DiscoveredAPI, error) {
	return nil, &UnsupportedError{"Discover"}
}
func (*EnvoyAdapter) ApplyPolicy(context.Context, string, string, PolicyAction) error {
	return &UnsupportedError{"ApplyPolicy"}
}
func (*EnvoyAdapter) RemovePolicy(context.Context, string, string, string) error {
	return &UnsupportedError{"RemovePolicy"}
}
func (*EnvoyAdapter) InjectCredentials(context.Context, string, []Credential) error {
	return &UnsupportedError{"InjectCredentials"}
}

func (a *EnvoyAdapter) SyncRoutes(ctx context.Context, _ string, routes []Route) (SyncResult, error) {
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
		converted = append(converted, xds.Route{ID: id, Path: path, Backend: r.BackendURL, Methods: append([]string(nil), r.Methods...)})
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
			if r.Activated && r.DeploymentID != "" {
				result.FailedRoutes[r.DeploymentID] = err.Error()
			}
		}
	}
	return result, err
}
