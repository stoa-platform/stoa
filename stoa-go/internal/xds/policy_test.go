package xds

import (
	"math"
	"net/netip"
	"testing"

	rbacconfig "github.com/envoyproxy/go-control-plane/envoy/config/rbac/v3"
	routepb "github.com/envoyproxy/go-control-plane/envoy/config/route/v3"
	cors "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/cors/v3"
	limit "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/local_ratelimit/v3"
	rbac "github.com/envoyproxy/go-control-plane/envoy/extensions/filters/http/rbac/v3"
	resource "github.com/envoyproxy/go-control-plane/pkg/resource/v3"
)

func TestRegressionCAB2280PolicyProjections(t *testing.T) {
	address := netip.AddrFrom4([4]byte{192, 0, 2, 7})
	for _, mode := range []string{"allow", "DENY"} {
		policies := []Policy{
			{ID: "cors", Type: "cors", Config: map[string]interface{}{"allowedOrigins": []string{"https://example.test", "*"}, "allowedMethods": []string{"GET", "POST"}, "maxAge": 60, "allowCredentials": true}},
			{ID: "limit", Type: "rate_limit", Config: map[string]interface{}{"maxRequests": 12, "intervalSeconds": 3}},
			{ID: "address", Type: "ip_filter", Config: map[string]interface{}{"mode": mode, "ip_list": []string{address.String(), netip.IPv6Loopback().String()}}},
		}
		configs, err := PolicyConfigs(policies)
		if err != nil {
			t.Fatal(err)
		}
		var c cors.CorsPolicy
		var l limit.LocalRateLimit
		var r rbac.RBACPerRoute
		if configs[corsFilter].UnmarshalTo(&c) != nil || configs[limitFilter].UnmarshalTo(&l) != nil || configs[rbacFilter].UnmarshalTo(&r) != nil {
			t.Fatal("invalid typed policy")
		}
		if c.AllowMethods != "GET,POST" || c.MaxAge != "60" || !c.AllowCredentials.Value || c.AllowOriginStringMatch[1].GetSafeRegex().Regex != ".*" {
			t.Fatal("CORS contract changed")
		}
		if l.TokenBucket.MaxTokens != 12 || l.TokenBucket.TokensPerFill.Value != 12 || l.TokenBucket.FillInterval.Seconds != 3 || l.FilterEnforced.DefaultValue.Numerator != 100 {
			t.Fatal("rate limit contract changed")
		}
		want := rbacconfig.RBAC_ALLOW
		if mode == "DENY" {
			want = rbacconfig.RBAC_DENY
		}
		principals := r.Rbac.Rules.Policies["stoa"].Principals
		if r.Rbac.Rules.Action != want || principals[0].GetDirectRemoteIp().PrefixLen.Value != 32 || principals[1].GetDirectRemoteIp().PrefixLen.Value != 128 {
			t.Fatal("direct peer address policy changed")
		}
		rs := routes()
		rs[0].Policies = policies
		snapshot, err := BuildSnapshot(config(), rs)
		if err != nil {
			t.Fatal(err)
		}
		foundPreflight := false
		for _, rsrc := range snapshot.GetResources(resource.RouteType) {
			config := rsrc.(*routepb.RouteConfiguration)
			for _, r := range config.VirtualHosts[0].Routes {
				if r.Name != rs[0].ID {
					continue
				}
				for _, header := range r.Match.Headers {
					if header.Name == ":method" && header.GetStringMatch().GetExact() == "OPTIONS" {
						if len(r.Match.Headers) != 3 {
							t.Fatal("implicit OPTIONS must only match a CORS preflight")
						}
						foundPreflight = true
					}
				}
			}
		}
		if !foundPreflight {
			t.Fatal("CORS preflight missing from method-constrained API route")
		}
		rs[0].Policies = []Policy{policies[2], policies[1], policies[0]}
		reordered, err := BuildSnapshot(config(), rs)
		if err != nil {
			t.Fatal(err)
		}
		if snapshot.GetVersion(resource.RouteType) != reordered.GetVersion(resource.RouteType) {
			t.Fatal("policy order changed version")
		}
		rs[0].Policies[1].Config["maxRequests"] = 13
		changed, err := BuildSnapshot(config(), rs)
		if err != nil {
			t.Fatal(err)
		}
		if snapshot.GetVersion(resource.RouteType) == changed.GetVersion(resource.RouteType) {
			t.Fatal("policy update did not change version")
		}
	}
}

func TestRegressionCAB2280RejectUnrepresentablePolicies(t *testing.T) {
	for _, policies := range [][]Policy{
		{{Type: "unknown"}},
		{{Type: "rate_limit", Config: map[string]interface{}{"maxRequests": uint64(math.MaxUint32) + 1, "intervalSeconds": 1}}},
		{{Type: "rate_limit", Config: map[string]interface{}{"maxRequests": 1, "intervalSeconds": math.MaxInt64}}},
		{{Type: "ip_filter", Config: map[string]interface{}{"mode": "allow", "ip_list": []string{"not-an-address"}}}},
		{{Type: "cors"}, {Type: "cors"}},
	} {
		if _, err := PolicyConfigs(policies); err == nil {
			t.Fatal("invalid or conflicting policy accepted")
		}
	}
}
