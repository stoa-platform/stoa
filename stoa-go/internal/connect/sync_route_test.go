package connect

import (
	"context"
	"errors"
	"testing"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// routeSyncMock is a GatewayAdapter stub for routeSyncer tests. syncRoutesErr
// is returned from SyncRoutes; if failedRoutes is non-nil, routeSyncMock
// also implements the adapter-local failedRoutesProvider interface.
type routeSyncMock struct {
	capturedRoutes []adapters.Route
	syncRoutesErr  error
	failedRoutes   map[string]string // if nil, provider interface not satisfied
}

func (m *routeSyncMock) Detect(ctx context.Context, adminURL string) (bool, error) {
	return true, nil
}
func (m *routeSyncMock) Discover(ctx context.Context, adminURL string) ([]adapters.DiscoveredAPI, error) {
	return nil, nil
}
func (m *routeSyncMock) ApplyPolicy(ctx context.Context, adminURL, apiName string, policy adapters.PolicyAction) error {
	return nil
}
func (m *routeSyncMock) RemovePolicy(ctx context.Context, adminURL, apiName, policyType string) error {
	return nil
}
func (m *routeSyncMock) SyncRoutes(ctx context.Context, adminURL string, routes []adapters.Route) error {
	m.capturedRoutes = append(m.capturedRoutes, routes...)
	return m.syncRoutesErr
}
func (m *routeSyncMock) InjectCredentials(ctx context.Context, adminURL string, creds []adapters.Credential) error {
	return nil
}

// routeSyncMockWithFailed wraps routeSyncMock and additionally implements
// the failedRoutesProvider interface used by routeSyncer.
type routeSyncMockWithFailed struct {
	routeSyncMock
}

func (m *routeSyncMockWithFailed) GetFailedRoutes() map[string]string {
	return m.failedRoutes
}

func TestRouteSyncerAppliedBatch(t *testing.T) {
	m := &routeSyncMock{}
	s := newRouteSyncer(m)

	routes := []adapters.Route{
		{DeploymentID: "dep-1", Name: "api-a", Generation: 3},
		{DeploymentID: "dep-2", Name: "api-b", Generation: 7},
	}
	results, err := s.Sync(context.Background(), "http://gw", routes)
	if err != nil {
		t.Fatalf("unexpected syncErr: %v", err)
	}
	if len(results) != 2 {
		t.Fatalf("expected 2 results, got %d", len(results))
	}
	for i, r := range results {
		if r.Status != "applied" {
			t.Errorf("result %d: status=%q, want applied", i, r.Status)
		}
		if len(r.Steps) != 3 {
			t.Errorf("result %d: expected 3 steps, got %d", i, len(r.Steps))
		}
	}
	// B.1 regression: Generation must be propagated to the ack.
	if results[0].Generation != 3 || results[1].Generation != 7 {
		t.Errorf("Generation not propagated: got %d, %d; want 3, 7", results[0].Generation, results[1].Generation)
	}
}

func TestRouteSyncerGlobalErrorFanOut(t *testing.T) {
	// Adapter without failedRoutesProvider (e.g. kong/gravitee). Global
	// sync error should fan out to all routes with status=failed.
	sentinel := errors.New("gateway unreachable")
	m := &routeSyncMock{syncRoutesErr: sentinel}
	s := newRouteSyncer(m)

	routes := []adapters.Route{
		{DeploymentID: "dep-1", Name: "api-a"},
		{DeploymentID: "dep-2", Name: "api-b"},
	}
	results, err := s.Sync(context.Background(), "http://gw", routes)
	if !errors.Is(err, sentinel) {
		t.Errorf("expected syncErr to surface, got %v", err)
	}
	for i, r := range results {
		if r.Status != "failed" {
			t.Errorf("result %d: status=%q, want failed", i, r.Status)
		}
		if r.Error != sentinel.Error() {
			t.Errorf("result %d: error=%q, want %q", i, r.Error, sentinel.Error())
		}
	}
}

func TestRouteSyncerPerRouteFailure(t *testing.T) {
	// Adapter WITH failedRoutesProvider (webmethods-style). Only dep-2 fails.
	m := &routeSyncMockWithFailed{
		routeSyncMock: routeSyncMock{syncRoutesErr: errors.New("partial failure")},
	}
	m.failedRoutes = map[string]string{"dep-2": "route conflict"}
	s := newRouteSyncer(m)

	routes := []adapters.Route{
		{DeploymentID: "dep-1", Name: "api-a"},
		{DeploymentID: "dep-2", Name: "api-b"},
	}
	results, _ := s.Sync(context.Background(), "http://gw", routes)

	if results[0].Status != "applied" {
		t.Errorf("dep-1 should be applied, got %q", results[0].Status)
	}
	if results[1].Status != "failed" || results[1].Error != "route conflict" {
		t.Errorf("dep-2 should be failed with 'route conflict', got status=%q err=%q", results[1].Status, results[1].Error)
	}
}

func TestRouteSyncerSkipsMissingDeploymentID(t *testing.T) {
	m := &routeSyncMock{}
	s := newRouteSyncer(m)

	// First route lacks deployment_id and must be dropped from results.
	routes := []adapters.Route{
		{DeploymentID: "", Name: "orphan"},
		{DeploymentID: "dep-1", Name: "tracked"},
	}
	results, _ := s.Sync(context.Background(), "http://gw", routes)

	if len(results) != 1 {
		t.Fatalf("expected 1 result (orphan dropped), got %d", len(results))
	}
	if results[0].DeploymentID != "dep-1" {
		t.Errorf("wrong route kept: %q", results[0].DeploymentID)
	}
	// Adapter still receives all routes (only the ack side filters).
	if len(m.capturedRoutes) != 2 {
		t.Errorf("adapter should see all 2 routes, got %d", len(m.capturedRoutes))
	}
}

func TestRouteSyncerEmpty(t *testing.T) {
	m := &routeSyncMock{}
	s := newRouteSyncer(m)
	results, err := s.Sync(context.Background(), "http://gw", nil)
	if err != nil || results != nil {
		t.Errorf("expected (nil, nil), got (%v, %v)", results, err)
	}
	if len(m.capturedRoutes) != 0 {
		t.Errorf("adapter should not be called on empty input, got %d routes", len(m.capturedRoutes))
	}
}

func TestRouteSyncerStepsReflectOutcome(t *testing.T) {
	// Success: api_synced=success with no detail
	m := &routeSyncMock{}
	s := newRouteSyncer(m)
	routes := []adapters.Route{{DeploymentID: "dep-1"}}
	results, _ := s.Sync(context.Background(), "http://gw", routes)
	if got := results[0].Steps[2]; got.Name != "api_synced" || got.Status != "success" || got.Detail != "" {
		t.Errorf("success steps[2]: %+v", got)
	}

	// Failure: api_synced=failed with error detail
	mFail := &routeSyncMock{syncRoutesErr: errors.New("boom")}
	sFail := newRouteSyncer(mFail)
	resultsFail, _ := sFail.Sync(context.Background(), "http://gw", routes)
	if got := resultsFail[0].Steps[2]; got.Name != "api_synced" || got.Status != "failed" || got.Detail != "boom" {
		t.Errorf("failure steps[2]: %+v", got)
	}
}
