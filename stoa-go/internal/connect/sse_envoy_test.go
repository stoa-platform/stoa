package connect

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
	"github.com/stoa-platform/stoa-go/internal/xds"
)

// The wire/ADS integration is covered separately; this recorder exposes the
// complete table handed to ADS, including unintended losses between events.
type routeTableRecorder struct {
	routes []xds.Route
	calls  int
	nack   bool
}

func TestRegressionCAB2256ReconnectAfterSubscription(t *testing.T) {
	s := &routeTableRecorder{}
	configReads := 0
	cp := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/v1/internal/gateways/own/events":
			w.Header().Set("Content-Type", "text/event-stream")
			// A publication in the former pre-connect gap is now in the config.
			_, _ = fmt.Fprint(w, "event: heartbeat\ndata: {\"status\":\"connected\"}\n\n")
		case "/v1/internal/gateways/own/config":
			configReads++
			_, _ = fmt.Fprint(w, `{"pending_deployments":[{"id":"missed","desired_generation":2,"desired_state":{"api_catalog_id":"orders","api_id":"orders","tenant_id":"o1-test","backend_url":"http://backend:8080","activated":true}}]}`)
		default:
			w.WriteHeader(http.StatusOK)
		}
	}))
	defer cp.Close()
	a := New(Config{ControlPlaneURL: cp.URL})
	a.state.SetGatewayID("own")
	for i := 0; i < 2; i++ {
		_ = a.streamEvents(context.Background(), adapters.NewEnvoyAdapter(s), "unused")
		if len(s.routes) != 1 || s.routes[0].ID != "orders" {
			t.Fatal("reconnect missed committed route")
		}
	}
	if configReads != 2 {
		t.Fatalf("catch-up must happen after every subscription: %d", configReads)
	}
}

func TestRegressionCAB2256GuardRollbackAndStaleEvents(t *testing.T) {
	s := &routeTableRecorder{}
	a := adapters.NewEnvoyAdapter(s)
	ctx := context.Background()
	r := adapters.Route{TenantID: "o1-test", APICatalogID: "11111111-1111-4111-8111-111111111111", ID: "one", DeploymentID: "dep", APIID: "one", BackendURL: "http://backend:8080", Activated: true, Generation: 1}
	if _, err := a.SyncRouteEvent(ctx, r); err != nil {
		t.Fatal(err)
	}
	calls := s.calls
	invalid := r
	invalid.Activated = false
	invalid.Generation++
	if _, err := a.SyncRouteEvent(ctx, invalid); err == nil || s.calls != calls {
		t.Fatal("inactive publication erased a route without an explicit tombstone")
	}
	if _, err := a.SyncRoutes(ctx, "", []adapters.Route{invalid}); err == nil || s.calls != calls {
		t.Fatal("inactive table erased a route without an explicit tombstone")
	}
	if _, err := a.SyncRoutes(ctx, "", nil); err == nil || s.calls != calls {
		t.Fatal("unexplained zero routes reached ADS")
	}
	s.nack = true
	second := r
	second.ID = "two"
	second.APICatalogID = "22222222-2222-4222-8222-222222222222"
	second.APIID = "two"
	second.DeploymentID = "second"
	if result, err := a.SyncRouteEvent(ctx, second); err == nil || result.FailedRoutes["second"] == "" {
		t.Fatal("NACK marked applied")
	}
	s.nack = false
	r.Activated = false
	r.Removing = true
	r.Generation = 2
	if _, err := a.SyncRouteEvent(ctx, r); err != nil || len(s.routes) != 0 {
		t.Fatal("failed proposal polluted acknowledged state")
	}
	calls = s.calls
	r.Activated = true
	r.Removing = false
	r.Generation = 1
	if _, err := a.SyncRouteEvent(ctx, r); err != nil || s.calls != calls {
		t.Fatal("queued pre-reconnect event resurrected deleted route")
	}
}

func (s *routeTableRecorder) Update(_ context.Context, routes []xds.Route) (string, error) {
	s.routes = append([]xds.Route(nil), routes...)
	s.calls++
	return "version", nil
}
func (s *routeTableRecorder) WaitAck(context.Context, string, time.Duration) error {
	if s.nack {
		return errors.New("rejected")
	}
	return nil
}

func TestRegressionCAB2256EnvoySSECompleteTable(t *testing.T) {
	a := New(Config{})
	a.state.SetGatewayID("own")
	s := &routeTableRecorder{}
	adapter := adapters.NewEnvoyAdapter(s)
	d := a.newSSEDispatcher(adapter, "unused")
	for i := 1; i <= 10; i++ {
		desired, _ := json.Marshal(adapters.Route{TenantID: "o1-test", APICatalogID: fmt.Sprint(i), APIID: fmt.Sprint(i), BackendURL: "http://backend:8080", Activated: true})
		data, _ := json.Marshal(DeploymentEvent{DeploymentID: fmt.Sprint(i), GatewayInstanceID: "own", DesiredState: desired})
		d.Dispatch(context.Background(), rawEvent{Type: "sync-deployment", Data: data})
		if len(s.routes) != i {
			t.Fatalf("publication %d: got %d routes", i, len(s.routes))
		}
	}
	before := s.calls
	data := []byte(`{"deployment_id":"foreign","gateway_instance_id":"other","desired_state":{"api_catalog_id":"foreign","api_id":"foreign","tenant_id":"other-tenant","backend_url":"http://backend:8080","activated":true}}`)
	d.Dispatch(context.Background(), rawEvent{Type: "sync-deployment", Data: data})
	if s.calls != before {
		t.Fatal("foreign gateway changed snapshot")
	}
	for i := 1; i <= 10; i++ {
		data, _ := json.Marshal(DeploymentEvent{DeploymentID: fmt.Sprint(i), APICatalogID: fmt.Sprint(i), GatewayInstanceID: "own", SyncStatus: "deleting"})
		d.Dispatch(context.Background(), rawEvent{Type: "undeploy", Data: data})
		if len(s.routes) != 10-i {
			t.Fatalf("removal %d: got %d routes", i, len(s.routes))
		}
	}
}
