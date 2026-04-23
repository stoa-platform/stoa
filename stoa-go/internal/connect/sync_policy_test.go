package connect

import (
	"context"
	"errors"
	"testing"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// policyMock implements GatewayAdapter. It captures every apply/remove call
// so tests can assert which dispatch branch was taken.
type policyMock struct {
	applied        []string // "apiName:policyType"
	removed        []string // "apiName:policyType"
	applyErr       error
	removeErr      error
	syncRoutesErr  error
	injectCredsErr error
}

func (m *policyMock) Detect(ctx context.Context, adminURL string) (bool, error) {
	return true, nil
}
func (m *policyMock) Discover(ctx context.Context, adminURL string) ([]adapters.DiscoveredAPI, error) {
	return nil, nil
}
func (m *policyMock) ApplyPolicy(ctx context.Context, adminURL, apiName string, p adapters.PolicyAction) error {
	m.applied = append(m.applied, apiName+":"+p.Type)
	return m.applyErr
}
func (m *policyMock) RemovePolicy(ctx context.Context, adminURL, apiName, policyType string) error {
	m.removed = append(m.removed, apiName+":"+policyType)
	return m.removeErr
}
func (m *policyMock) SyncRoutes(ctx context.Context, adminURL string, routes []adapters.Route) (adapters.SyncResult, error) {
	return adapters.SyncResult{FailedRoutes: map[string]string{}}, m.syncRoutesErr
}
func (m *policyMock) InjectCredentials(ctx context.Context, adminURL string, creds []adapters.Credential) error {
	return m.injectCredsErr
}

// policyMockOIDC wraps policyMock and additionally implements OIDCAdapter.
// Each typed method records its arguments so tests can assert dispatch
// went through the OIDC-specific path, not the generic fallback.
type policyMockOIDC struct {
	policyMock
	authServerSpecs []adapters.AuthServerSpec
	strategySpecs   []adapters.StrategySpec
	scopeSpecs      []adapters.ScopeSpec
	deletedServers  []string
}

func (m *policyMockOIDC) UpsertAuthServer(ctx context.Context, adminURL string, spec adapters.AuthServerSpec) error {
	m.authServerSpecs = append(m.authServerSpecs, spec)
	return nil
}
func (m *policyMockOIDC) UpsertStrategy(ctx context.Context, adminURL string, spec adapters.StrategySpec) error {
	m.strategySpecs = append(m.strategySpecs, spec)
	return nil
}
func (m *policyMockOIDC) UpsertScope(ctx context.Context, adminURL string, spec adapters.ScopeSpec) error {
	m.scopeSpecs = append(m.scopeSpecs, spec)
	return nil
}
func (m *policyMockOIDC) DeleteAuthServer(ctx context.Context, adminURL, name string) error {
	m.deletedServers = append(m.deletedServers, name)
	return nil
}

// --- Apply dispatch ---

func TestPolicySyncerAppliesGeneric(t *testing.T) {
	m := &policyMock{}
	s := newPolicySyncer(m)
	results := s.SyncPolicies(context.Background(), "http://gw", []PendingPolicy{
		{ID: "p1", Name: "rate-limit", PolicyType: "rate_limit", Enabled: true, Config: map[string]interface{}{"rpm": 100}},
	})
	if len(results) != 1 || results[0].Status != "applied" {
		t.Errorf("expected 1 applied result, got %+v", results)
	}
	if len(m.applied) != 1 || m.applied[0] != "rate-limit:rate_limit" {
		t.Errorf("generic ApplyPolicy not called correctly: %v", m.applied)
	}
}

func TestPolicySyncerAppliesOIDCAuthServer(t *testing.T) {
	m := &policyMockOIDC{}
	s := newPolicySyncer(m)
	s.SyncPolicies(context.Background(), "http://gw", []PendingPolicy{{
		ID:         "p1",
		Name:       "primary-idp",
		PolicyType: "oidc_auth_server",
		Enabled:    true,
		Config: map[string]interface{}{
			"discovery_url": "https://kc.example/.well-known",
			"client_id":     "cid",
			"client_secret": "csec",
			"scopes":        []interface{}{"openid", "profile"},
		},
	}})
	if len(m.authServerSpecs) != 1 {
		t.Fatalf("UpsertAuthServer not called, got %d calls", len(m.authServerSpecs))
	}
	spec := m.authServerSpecs[0]
	if spec.Name != "primary-idp" || spec.DiscoveryURL != "https://kc.example/.well-known" {
		t.Errorf("wrong spec: %+v", spec)
	}
	if len(spec.Scopes) != 2 || spec.Scopes[0] != "openid" {
		t.Errorf("scopes not decoded from []interface{}: %v", spec.Scopes)
	}
	if len(m.applied) != 0 {
		t.Errorf("generic ApplyPolicy should NOT be called on OIDC type, got %v", m.applied)
	}
}

func TestPolicySyncerAppliesOIDCStrategy(t *testing.T) {
	m := &policyMockOIDC{}
	s := newPolicySyncer(m)
	s.SyncPolicies(context.Background(), "http://gw", []PendingPolicy{{
		ID:         "p1",
		Name:       "strat-a",
		PolicyType: "oidc_strategy",
		Enabled:    true,
		Config: map[string]interface{}{
			"auth_server_alias": "primary-idp",
			"client_id":         "strat-client",
			"audience":          "api-x",
		},
	}})
	if len(m.strategySpecs) != 1 || m.strategySpecs[0].AuthServerAlias != "primary-idp" {
		t.Errorf("UpsertStrategy not called correctly: %+v", m.strategySpecs)
	}
}

func TestPolicySyncerAppliesOIDCScope(t *testing.T) {
	m := &policyMockOIDC{}
	s := newPolicySyncer(m)
	s.SyncPolicies(context.Background(), "http://gw", []PendingPolicy{{
		ID:         "p1",
		Name:       "scope-a",
		PolicyType: "oidc_scope",
		Enabled:    true,
		Config: map[string]interface{}{
			"scope_name":        "read:api",
			"audience":          "api-x",
			"auth_server_alias": "primary-idp",
			"keycloak_scope":    "api-read",
		},
	}})
	if len(m.scopeSpecs) != 1 || m.scopeSpecs[0].ScopeName != "read:api" {
		t.Errorf("UpsertScope not called correctly: %+v", m.scopeSpecs)
	}
}

// TestPolicySyncerOIDCFallsBackWithoutAdapter covers the case where the CP
// emits an OIDC policy type but the local adapter does not implement
// OIDCAdapter — the policy must fall through to generic ApplyPolicy rather
// than crash with a nil dereference.
func TestPolicySyncerOIDCFallsBackWithoutAdapter(t *testing.T) {
	m := &policyMock{} // NOT OIDC
	s := newPolicySyncer(m)
	s.SyncPolicies(context.Background(), "http://gw", []PendingPolicy{{
		ID:         "p1",
		Name:       "strat-a",
		PolicyType: "oidc_strategy",
		Enabled:    true,
		Config:     map[string]interface{}{},
	}})
	if len(m.applied) != 1 || m.applied[0] != "strat-a:oidc_strategy" {
		t.Errorf("expected generic ApplyPolicy fallback, got %v", m.applied)
	}
}

// --- Remove dispatch ---

func TestPolicySyncerRemovesGeneric(t *testing.T) {
	m := &policyMock{}
	s := newPolicySyncer(m)
	results := s.SyncPolicies(context.Background(), "http://gw", []PendingPolicy{
		{ID: "p1", Name: "rate-limit", PolicyType: "rate_limit", Enabled: false},
	})
	if results[0].Status != "removed" {
		t.Errorf("expected removed, got %q", results[0].Status)
	}
	if len(m.removed) != 1 || m.removed[0] != "rate-limit:rate_limit" {
		t.Errorf("generic RemovePolicy not called: %v", m.removed)
	}
}

func TestPolicySyncerRemovesOIDCAuthServer(t *testing.T) {
	m := &policyMockOIDC{}
	s := newPolicySyncer(m)
	s.SyncPolicies(context.Background(), "http://gw", []PendingPolicy{
		{ID: "p1", Name: "primary-idp", PolicyType: "oidc_auth_server", Enabled: false},
	})
	if len(m.deletedServers) != 1 || m.deletedServers[0] != "primary-idp" {
		t.Errorf("DeleteAuthServer not called correctly: %v", m.deletedServers)
	}
	if len(m.removed) != 0 {
		t.Errorf("generic RemovePolicy should NOT be called for oidc_auth_server, got %v", m.removed)
	}
}

// TestPolicySyncerRemovesOIDCStrategyViaGenericFallback documents the
// asymmetry in the OIDCAdapter interface (C.1 in REWRITE-BUGS.md):
// DeleteStrategy/DeleteScope do not exist, so disabling an oidc_strategy
// falls through to adapter.RemovePolicy with the type as a hint. Whether
// the concrete adapter handles or no-ops is adapter-specific (GO-1 scope).
func TestPolicySyncerRemovesOIDCStrategyViaGenericFallback(t *testing.T) {
	m := &policyMockOIDC{}
	s := newPolicySyncer(m)
	s.SyncPolicies(context.Background(), "http://gw", []PendingPolicy{
		{ID: "p1", Name: "strat-a", PolicyType: "oidc_strategy", Enabled: false},
	})
	// Went through generic RemovePolicy (not a typed OIDC method).
	if len(m.removed) != 1 || m.removed[0] != "strat-a:oidc_strategy" {
		t.Errorf("expected generic RemovePolicy fallback, got %v", m.removed)
	}
	if len(m.deletedServers) != 0 {
		t.Errorf("DeleteAuthServer should NOT be called for oidc_strategy, got %v", m.deletedServers)
	}
}

// --- Failure handling ---

func TestPolicySyncerFailedApplyProducesFailedResult(t *testing.T) {
	m := &policyMock{applyErr: errors.New("gateway 500")}
	s := newPolicySyncer(m)
	results := s.SyncPolicies(context.Background(), "http://gw", []PendingPolicy{
		{ID: "p1", Name: "x", PolicyType: "generic", Enabled: true},
	})
	if results[0].Status != "failed" || results[0].Error != "gateway 500" {
		t.Errorf("expected failed/gateway 500, got %+v", results[0])
	}
}

func TestPolicySyncerFailedRemoveProducesFailedResult(t *testing.T) {
	m := &policyMock{removeErr: errors.New("not found")}
	s := newPolicySyncer(m)
	results := s.SyncPolicies(context.Background(), "http://gw", []PendingPolicy{
		{ID: "p1", Name: "x", PolicyType: "generic", Enabled: false},
	})
	if results[0].Status != "failed" || results[0].Error != "not found" {
		t.Errorf("expected failed/not found, got %+v", results[0])
	}
}

// --- Config helpers ---

func TestGetStringConfigFallback(t *testing.T) {
	m := map[string]interface{}{"key": "value", "wrong_type": 42}
	if got := getStringConfig(m, "key"); got != "value" {
		t.Errorf("got %q, want 'value'", got)
	}
	if got := getStringConfig(m, "missing"); got != "" {
		t.Errorf("got %q, want ''", got)
	}
	if got := getStringConfig(m, "wrong_type"); got != "" {
		t.Errorf("got %q, want '' for non-string", got)
	}
}

func TestGetStringSliceConfigVariants(t *testing.T) {
	tests := []struct {
		name string
		in   interface{}
		want []string
	}{
		{"native []string", []string{"a", "b"}, []string{"a", "b"}},
		{"JSON []interface{}", []interface{}{"a", "b"}, []string{"a", "b"}},
		{"mixed types skipped", []interface{}{"a", 42, "b"}, []string{"a", "b"}},
		{"wrong outer type", "just-a-string", nil},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			m := map[string]interface{}{"scopes": tc.in}
			got := getStringSliceConfig(m, "scopes")
			if len(got) != len(tc.want) {
				t.Fatalf("len mismatch: got %v, want %v", got, tc.want)
			}
			for i := range got {
				if got[i] != tc.want[i] {
					t.Errorf("[%d]: got %q, want %q", i, got[i], tc.want[i])
				}
			}
		})
	}
}
