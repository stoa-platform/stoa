package connect

import (
	"context"
	"testing"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

func TestRegressionCAB2280AttributedPolicySet(t *testing.T) {
	ctx := context.Background()
	s := &routeTableRecorder{}
	a := adapters.NewEnvoyAdapter(s)
	_, err := a.SyncRoutes(ctx, "", []adapters.Route{
		{ID: "one", DeploymentID: "one", APIID: "one", BackendURL: "http://backend:8080", Activated: true, TenantID: "tenant"},
		{ID: "two", DeploymentID: "two", APIID: "two", BackendURL: "http://backend:8080", Activated: true, TenantID: "other"},
	})
	if err != nil {
		t.Fatal(err)
	}
	yes := true
	p := PendingPolicy{ID: "cors", PolicyType: "cors", Enabled: true, Scope: "tenant", TenantID: "tenant", Applicable: &yes, Config: map[string]interface{}{}}
	syncer := newPolicySyncer(a)
	result := syncer.SyncPolicies(ctx, "", []PendingPolicy{p})
	if result[0].Status != "applied" || len(s.routes[0].Policies) != 1 || len(s.routes[1].Policies) != 0 {
		t.Fatal("policy crossed tenant boundary")
	}
	before := s.calls
	unsupported := p
	unsupported.ID = "jwt"
	unsupported.PolicyType = "jwt_validation"
	result = syncer.SyncPolicies(ctx, "", []PendingPolicy{p, unsupported})
	if result[0].Status != "failed" || result[1].Error != "unsupported policy" || s.calls != before {
		t.Fatal("unsupported batch partially published")
	}
	p.Applicable = nil
	result = syncer.SyncPolicies(ctx, "", []PendingPolicy{p})
	if result[0].Status != "failed" || s.calls != before {
		t.Fatal("missing inventory metadata accepted")
	}
	syncer.SyncPolicies(ctx, "", nil)
	if len(s.routes[0].Policies) != 0 {
		t.Fatal("absent policy survived inventory replacement")
	}
	for _, kind := range []string{"logging", "jwt_validation", "jwt", "oidc_auth_server", "oidc_strategy", "oidc_scope", "caching", "transform"} {
		before = s.calls
		_, err := adapters.PreparePolicy(a, adapters.PolicyAction{Type: kind})
		contract, ok := err.(*adapters.PolicyError)
		if !ok || contract.Code != "unsupported" || s.calls != before {
			t.Fatalf("type %s was not refused locally", kind)
		}
	}
}
