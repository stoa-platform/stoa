package adapters

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/stoa-platform/stoa-go/internal/xds"
)

type policySnapshotRecorder struct {
	routes []xds.Route
	calls  int
	nack   bool
}

func (s *policySnapshotRecorder) Update(_ context.Context, r []xds.Route) (string, error) {
	s.routes = r
	s.calls++
	return "v", nil
}
func (s *policySnapshotRecorder) WaitAck(context.Context, string, time.Duration) error {
	if s.nack {
		return errors.New("rejected")
	}
	return nil
}

func TestRegressionCAB2280EnvoyPolicyTranslation(t *testing.T) {
	ctx := context.Background()
	s := &policySnapshotRecorder{}
	a := NewEnvoyAdapter(s)
	routes := []Route{{ID: "catalog", APICatalogID: "catalog", DeploymentID: "dep", APIID: "orders", TenantID: "tenant", BackendURL: "http://backend:8080", Activated: true}}
	if _, err := a.SyncRoutes(ctx, "", routes); err != nil {
		t.Fatal(err)
	}
	p := PolicyAction{ID: "cors", Type: "cors", Scope: "api", Targets: []string{"catalog"}, Config: map[string]interface{}{}}
	if err := a.ApplyPolicy(ctx, "", "display-name", p); err != nil {
		t.Fatalf("translation not applied: %v", err)
	}
	if len(s.routes[0].Policies) != 1 || s.routes[0].Policies[0].ID != "cors" {
		t.Fatal("policy attribution missing")
	}
	before := s.calls
	p.ID = "conflict"
	if err := a.ApplyPolicy(ctx, "", "other-name", p); err == nil || s.calls != before {
		t.Fatal("conflicting CORS emitted")
	}
	p.ID = "missing"
	p.Targets = []string{"other"}
	if err := a.ApplyPolicy(ctx, "", "ignored", p); err == nil || s.calls != before {
		t.Fatal("unbound API policy broadened")
	}
	p.ID = "cors"
	p.Targets = []string{"catalog"}
	p.Config = map[string]interface{}{"allowedOrigins": []string{"https://new.example.test"}}
	s.nack = true
	if err := a.ApplyPolicy(ctx, "", "ignored", p); err == nil {
		t.Fatal("NACK marked applied")
	}
	s.nack = false
	if _, err := a.SyncRoutes(ctx, "", routes); err != nil {
		t.Fatal(err)
	}
	if len(s.routes[0].Policies[0].Config["allowedOrigins"].([]interface{})) != 1 {
		t.Fatal("last good policy not retained")
	}
	if err := a.RemovePolicy(ctx, "", "cors", "cors"); err != nil || len(s.routes[0].Policies) != 0 {
		t.Fatal("precise removal failed")
	}
}
