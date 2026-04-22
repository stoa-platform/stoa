package connect

import (
	"context"
	"log"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// policySyncer reconciles one config cycle worth of PendingPolicy entries
// against the local gateway adapter. Dispatch splits along two axes:
//
//  1. enabled vs disabled (apply vs remove)
//  2. policy type + adapter capability (OIDC-aware vs generic)
//
// Each dispatch branch is its own typed method (applyAuthServer,
// applyStrategy, applyScope, removePolicy, ...), so adding or
// regression-testing a single branch is a ~15-LOC operation.
//
// policySyncer is stateless beyond the one-time OIDCAdapter type-assert
// cached at construction.
type policySyncer struct {
	adapter     adapters.GatewayAdapter
	oidcAdapter adapters.OIDCAdapter // nil if adapter does not implement OIDCAdapter
}

func newPolicySyncer(adapter adapters.GatewayAdapter) *policySyncer {
	oidc, _ := adapter.(adapters.OIDCAdapter)
	return &policySyncer{adapter: adapter, oidcAdapter: oidc}
}

func (s *policySyncer) hasOIDC() bool { return s.oidcAdapter != nil }

// SyncPolicies returns one SyncedPolicyResult per input policy. The caller
// is responsible for updating Prometheus counters and sending the ack —
// policySyncer is pure dispatch + per-policy logging.
func (s *policySyncer) SyncPolicies(ctx context.Context, adminURL string, policies []PendingPolicy) []SyncedPolicyResult {
	results := make([]SyncedPolicyResult, 0, len(policies))
	for _, p := range policies {
		results = append(results, s.syncOne(ctx, adminURL, p))
	}
	return results
}

func (s *policySyncer) syncOne(ctx context.Context, adminURL string, p PendingPolicy) SyncedPolicyResult {
	result := SyncedPolicyResult{PolicyID: p.ID}

	var err error
	successStatus := "applied"
	if !p.Enabled {
		successStatus = "removed"
		err = s.remove(ctx, adminURL, p)
	} else {
		err = s.apply(ctx, adminURL, p)
	}

	if err != nil {
		result.Status = "failed"
		result.Error = err.Error()
		// Log reads naturally whether we attempted apply or remove.
		verb := "apply"
		if !p.Enabled {
			verb = "remove"
		}
		log.Printf("sync: %s policy %s failed: %v", verb, p.Name, err)
		return result
	}

	result.Status = successStatus
	log.Printf("sync: %s policy %s (%s)", successStatus, p.Name, p.PolicyType)
	return result
}

// apply routes an enabled PendingPolicy through the typed OIDC handlers
// (if the adapter supports OIDC) or the generic ApplyPolicy entry.
func (s *policySyncer) apply(ctx context.Context, adminURL string, p PendingPolicy) error {
	switch {
	case p.PolicyType == "oidc_auth_server" && s.hasOIDC():
		return s.applyAuthServer(ctx, adminURL, p)
	case p.PolicyType == "oidc_strategy" && s.hasOIDC():
		return s.applyStrategy(ctx, adminURL, p)
	case p.PolicyType == "oidc_scope" && s.hasOIDC():
		return s.applyScope(ctx, adminURL, p)
	default:
		return s.adapter.ApplyPolicy(ctx, adminURL, p.Name, adapters.PolicyAction{
			Type:   p.PolicyType,
			Config: p.Config,
		})
	}
}

// remove routes a disabled PendingPolicy. Only oidc_auth_server has a
// dedicated Delete on OIDCAdapter (DeleteStrategy / DeleteScope don't
// exist on the interface — see REWRITE-BUGS.md C.1). All other types
// fall through to the adapter's generic RemovePolicy, which is expected
// to handle or no-op based on the policyType hint.
func (s *policySyncer) remove(ctx context.Context, adminURL string, p PendingPolicy) error {
	if p.PolicyType == "oidc_auth_server" && s.hasOIDC() {
		return s.oidcAdapter.DeleteAuthServer(ctx, adminURL, p.Name)
	}
	return s.adapter.RemovePolicy(ctx, adminURL, p.Name, p.PolicyType)
}

// --- Typed apply handlers ---

func (s *policySyncer) applyAuthServer(ctx context.Context, adminURL string, p PendingPolicy) error {
	return s.oidcAdapter.UpsertAuthServer(ctx, adminURL, adapters.AuthServerSpec{
		Name:         p.Name,
		DiscoveryURL: getStringConfig(p.Config, "discovery_url"),
		ClientID:     getStringConfig(p.Config, "client_id"),
		ClientSecret: getStringConfig(p.Config, "client_secret"),
		Scopes:       getStringSliceConfig(p.Config, "scopes"),
	})
}

func (s *policySyncer) applyStrategy(ctx context.Context, adminURL string, p PendingPolicy) error {
	return s.oidcAdapter.UpsertStrategy(ctx, adminURL, adapters.StrategySpec{
		Name:            p.Name,
		AuthServerAlias: getStringConfig(p.Config, "auth_server_alias"),
		ClientID:        getStringConfig(p.Config, "client_id"),
		Audience:        getStringConfig(p.Config, "audience"),
	})
}

func (s *policySyncer) applyScope(ctx context.Context, adminURL string, p PendingPolicy) error {
	return s.oidcAdapter.UpsertScope(ctx, adminURL, adapters.ScopeSpec{
		ScopeName:       getStringConfig(p.Config, "scope_name"),
		Audience:        getStringConfig(p.Config, "audience"),
		AuthServerAlias: getStringConfig(p.Config, "auth_server_alias"),
		KeycloakScope:   getStringConfig(p.Config, "keycloak_scope"),
	})
}

// --- Config helpers (moved from sync.go; only used by policy dispatch) ---

// getStringConfig safely extracts a string value from a config map.
func getStringConfig(config map[string]interface{}, key string) string {
	if v, ok := config[key]; ok {
		if s, ok := v.(string); ok {
			return s
		}
	}
	return ""
}

// getStringSliceConfig safely extracts a string slice from a config map.
// Accepts either []string (native) or []interface{} of strings (JSON-decoded).
func getStringSliceConfig(config map[string]interface{}, key string) []string {
	v, ok := config[key]
	if !ok {
		return nil
	}
	switch val := v.(type) {
	case []string:
		return val
	case []interface{}:
		var result []string
		for _, item := range val {
			if s, ok := item.(string); ok {
				result = append(result, s)
			}
		}
		return result
	default:
		return nil
	}
}
