//go:build o1integration

package connect

import (
	"net/http"
	"time"
)

func init() { o1PoliciesPhase = runO1Policies }

func runO1Policies(f o1PolicyFixture) (map[string]interface{}, func()) {
	t, request, state, eventually, call := f.t, f.request, f.state, f.eventually, f.call
	authorization, upstreamCalls := f.authorization, f.upstreamCalls
	get := func(path string, headers map[string]string) (int, http.Header) {
		return call(http.MethodGet, path, headers)
	}
	var code int
	type policyEvidence struct {
		ID      string   `json:"id"`
		Type    string   `json:"type"`
		Scope   string   `json:"scope"`
		Targets []string `json:"targets"`
	}
	policyInventory := make(map[string]policyEvidence)
	recordPolicy := func(id string) {
		t.Helper()
		var config GatewayConfigResponse
		request("GET", "/v1/internal/gateways/"+f.gatewayID+"/config", nil, &config)
		for _, p := range config.PendingPolicies {
			if p.ID == id && p.Enabled && p.Applicable != nil && *p.Applicable {
				policyInventory[id] = policyEvidence{ID: p.ID, Type: p.PolicyType, Scope: p.Scope, Targets: append([]string(nil), p.APICatalogIDs...)}
				return
			}
		}
		t.Fatal("tested policy missing from CP enabled/applicable inventory")
	}
	policy := func(kind string, config map[string]interface{}, id string) string {
		body := map[string]interface{}{"type": kind, "target": f.targetCatalog, "config": config}
		if id != "" {
			body["id"] = id
		}
		var result struct{ ID string }
		request("POST", "/o1/policy", body, &result)
		return result.ID
	}
	waitFilter := func(name string, present bool) {
		eventually(5*time.Second, "policy filter state", func() bool { _, exists := state().routes[f.targetCatalog].Typed[name]; return exists == present })
	}
	corsName := "envoy.filters.http.cors"
	rateName := "envoy.filters.http.local_ratelimit"
	rbacName := "envoy.filters.http.rbac"
	corsID := policy("cors", map[string]interface{}{"allowedOrigins": []string{"https://client.example.test"}}, "")
	recordPolicy(corsID)
	waitFilter(corsName, true)
	eventually(5*time.Second, "CORS enforced by Envoy", func() bool {
		code, headers := get(f.targetPath, map[string]string{"Origin": "https://client.example.test"})
		return code == 200 && headers.Get("Access-Control-Allow-Origin") == "https://client.example.test"
	})
	beforeAllowedPreflightUpstream := upstreamCalls.Load()
	eventually(5*time.Second, "authorized CORS preflight answered without upstream", func() bool {
		code, headers := call(http.MethodOptions, f.targetPath, map[string]string{
			"Origin": "https://client.example.test", "Access-Control-Request-Method": "GET",
		})
		return code == http.StatusOK && headers.Get("Access-Control-Allow-Origin") == "https://client.example.test" && upstreamCalls.Load() == beforeAllowedPreflightUpstream
	})
	beforePlainOptionsUpstream := upstreamCalls.Load()
	plainOptionsCode, _ := call(http.MethodOptions, f.targetPath, nil)
	if plainOptionsCode != http.StatusNotFound || upstreamCalls.Load() != beforePlainOptionsUpstream {
		t.Fatal("plain OPTIONS matched implicit preflight route or reached upstream")
	}
	// A browser preflight must be authorized before CORS can answer it.
	authorization.mode.Store(1)
	beforePreflightAuth, beforePreflightUpstream := authorization.calls.Load(), upstreamCalls.Load()
	preflightCode, _ := call(http.MethodOptions, f.targetPath, map[string]string{
		"Origin": "https://client.example.test", "Access-Control-Request-Method": "GET",
	})
	authorization.mode.Store(0)
	if preflightCode != http.StatusForbidden || authorization.calls.Load() != beforePreflightAuth+1 || upstreamCalls.Load() != beforePreflightUpstream {
		t.Fatal("denied CORS preflight bypassed authorization or reached upstream")
	}
	rateID := policy("rate_limit", map[string]interface{}{"maxRequests": 2, "intervalSeconds": 60}, "")
	recordPolicy(rateID)
	waitFilter(rateName, true)
	for _, expected := range []int{200, 200, 429} {
		code, _ = get(f.targetPath, nil)
		if code != expected {
			t.Fatalf("local rate limit: got %d want %d", code, expected)
		}
	}
	request("DELETE", "/o1/policy/"+rateID, nil, nil)
	waitFilter(rateName, false)
	addressID := policy("ip_filter", map[string]interface{}{"mode": "allow", "ip_list": []string{}}, "")
	recordPolicy(addressID)
	waitFilter(rbacName, true)
	eventually(5*time.Second, "empty allow set denies", func() bool {
		code, _ := get(f.targetPath, nil)
		return code == 403
	})
	code, _ = get(f.otherPath, nil)
	if code != 200 {
		t.Fatal("API policy affected another route")
	}
	policy("ip_filter", map[string]interface{}{"mode": "deny", "ip_list": []string{}}, addressID)
	eventually(5*time.Second, "updated deny set", func() bool { code, _ := get(f.targetPath, nil); return code == 200 })
	unsupportedBefore := state().version
	unsupportedID := policy("jwt_validation", map[string]interface{}{"issuer": "https://issuer.example.test", "audience": "o1", "jwks_url": "https://issuer.example.test/jwks"}, "")
	eventually(5*time.Second, "unsupported policy failed locally", func() bool {
		var acks []SyncedPolicyResult
		request("GET", "/o1/acks", nil, &acks)
		for _, ack := range acks {
			if ack.PolicyID == unsupportedID && ack.Status == "failed" && ack.Error == "unsupported policy" {
				return true
			}
		}
		return false
	})
	if state().version != unsupportedBefore {
		t.Fatal("unsupported inventory changed snapshot")
	}
	request("DELETE", "/o1/policy/"+unsupportedID, nil, nil)
	return map[string]interface{}{
			"policies":                               []string{"cors", "rate_limit", "ip_filter"},
			"cp_enabled_applicable_policy_inventory": policyInventory,
			"cors_preflight_denial_authorized_without_upstream": true,
			"unsupported_failed_without_publication":            true,
		}, func() {
			request("DELETE", "/o1/policy/"+addressID, nil, nil)
			request("DELETE", "/o1/policy/"+corsID, nil, nil)
			waitFilter(corsName, false)
			waitFilter(rbacName, false)
		}
}
