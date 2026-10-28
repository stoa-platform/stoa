package adapters

import (
	"context"
	"encoding/json"
	"sort"

	"github.com/stoa-platform/stoa-go/internal/xds"
)

func (a *EnvoyAdapter) policiesForRoute(r Route) []xds.Policy {
	result := []xds.Policy{}
	for _, p := range a.policies {
		if p.TenantID != "" && p.TenantID != r.TenantID {
			continue
		}
		matches := p.Scope == "gateway" || p.Scope == "tenant"
		for _, id := range p.Targets {
			if id == r.APICatalogID || id == r.ID {
				matches = true
			}
		}
		if matches {
			result = append(result, xds.Policy{ID: p.ID, Type: p.Type, Config: p.Config})
		}
	}
	sort.Slice(result, func(i, j int) bool { return result[i].ID < result[j].ID })
	return result
}

func (a *EnvoyAdapter) prepareEnvoyPolicy(p PolicyAction) (PolicyAction, error) {
	p, err := PreparePolicy(a, p)
	if err != nil {
		return p, err
	}
	if p.ID == "" || (p.Scope != "api" && p.Scope != "gateway" && p.Scope != "tenant") || (p.Scope == "tenant" && p.TenantID == "") {
		return p, &PolicyError{Code: "invalid"}
	}
	if _, err = xds.PolicyConfigs([]xds.Policy{{ID: p.ID, Type: p.Type, Config: p.Config}}); err != nil {
		return p, &PolicyError{Code: "invalid"}
	}
	if p.Scope == "api" {
		for _, id := range p.Targets {
			if id == "" {
				return p, &PolicyError{Code: "invalid"}
			}
		}
		found := false
		for _, r := range a.routes {
			for _, id := range p.Targets {
				if r.Activated && (id == r.ID || id == r.APICatalogID) && (p.TenantID == "" || p.TenantID == r.TenantID) {
					found = true
				}
			}
		}
		if !found {
			return p, &PolicyError{Code: "not_found"}
		}
	}
	// Own all stored inputs, including arrays from decoded CP configurations.
	data, err := json.Marshal(p.Config)
	if err != nil {
		return p, &PolicyError{Code: "invalid"}
	}
	if err = json.Unmarshal(data, &p.Config); err != nil {
		return p, &PolicyError{Code: "invalid"}
	}
	p.Targets = append([]string(nil), p.Targets...)
	return p, nil
}

// ReconcilePolicies replaces the entire applicable active inventory atomically.
// A rejected batch retains the last acknowledged routes and policies.
func (a *EnvoyAdapter) ReconcilePolicies(ctx context.Context, policies []PolicyAction) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	next := map[string]PolicyAction{}
	for _, p := range policies {
		prepared, err := a.prepareEnvoyPolicy(p)
		if err != nil {
			return err
		}
		if _, duplicate := next[p.ID]; duplicate {
			return &PolicyError{Code: "invalid"}
		}
		next[p.ID] = prepared
	}
	return a.publishPolicies(ctx, next)
}

func (a *EnvoyAdapter) publishPolicies(ctx context.Context, next map[string]PolicyAction) error {
	old := a.policies
	a.policies = next
	if _, err := a.syncRoutes(ctx, a.routes); err != nil {
		a.policies = old
		return SafePolicyError(err)
	}
	return nil
}

func (a *EnvoyAdapter) ApplyPolicy(ctx context.Context, _ string, _ string, p PolicyAction) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	p, err := a.prepareEnvoyPolicy(p)
	if err != nil {
		return err
	}
	next := map[string]PolicyAction{}
	for id, old := range a.policies {
		next[id] = old
	}
	next[p.ID] = p
	return a.publishPolicies(ctx, next)
}

// Envoy removes by immutable policy ID; display names never identify targets.
func (a *EnvoyAdapter) RemovePolicy(ctx context.Context, _ string, id string, kind string) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	if _, known := policyConfigV1[kind]; !known {
		return &PolicyError{Code: "invalid"}
	}
	next := map[string]PolicyAction{}
	for oldID, p := range a.policies {
		if oldID != id {
			next[oldID] = p
		}
	}
	return a.publishPolicies(ctx, next)
}
