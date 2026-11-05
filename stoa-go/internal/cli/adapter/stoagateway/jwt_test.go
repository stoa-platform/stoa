package stoagateway

import (
	"maps"
	"reflect"
	"strings"
	"testing"
)

func TestRegressionAuthenticatedContractCopy(t *testing.T) {
	for _, tt := range []struct {
		name, class, audience, camel, snake, wantAudience, wantError string
		allow                                                        bool
	}{
		{name: "adapter audience", class: " h ", audience: " orders-read ", camel: "legacy-read", snake: "older-read", wantAudience: "orders-read"},
		{name: "camel audience", class: "VH", camel: " orders-read ", snake: "older-read", wantAudience: "orders-read"},
		{name: "snake audience", class: "VVH", snake: " orders-read ", wantAudience: "orders-read"},
		{name: "missing audience", class: "H", wantError: "specific inboundAuth audience required"},
		{name: "generic account", class: "H", camel: "AcCoUnT", wantError: "generic inboundAuth audience refused"},
		{name: "generic realm", class: "H", snake: "SANDBOX", wantError: "generic inboundAuth audience refused"},
		{name: "wildcard audience", class: "H", audience: "orders-*", wantError: "generic inboundAuth audience refused"},
		{name: "invalid override", class: "H", audience: "account", camel: "orders-read", wantError: "generic inboundAuth audience refused"},
		{name: "missing class", audience: "orders-read", wantError: "classification must be H, VH or VVH"},
		{name: "unknown class", class: "L", audience: "orders-read", wantError: "classification must be H, VH or VVH"},
		{name: "explicit H opt in", class: " h ", allow: true},
		{name: "authenticated H opt in", class: "H", allow: true, audience: "orders-read", wantAudience: "orders-read"},
		{name: "generic opt in refused", class: "H", allow: true, camel: "account", wantError: "generic inboundAuth audience refused"},
		{name: "VH opt in refused", class: "VH", allow: true, audience: "orders-read", wantError: "allowUnauthenticatedREST is restricted to classification H"},
		{name: "VVH opt in refused", class: "VVH", allow: true, audience: "orders-read", wantError: "allowUnauthenticatedREST is restricted to classification H"},
	} {
		t.Run(tt.name, func(t *testing.T) {
			desired := Contract{
				"name": "orders", "tenant_id": "sandbox", "version": "2",
				"description": "Order lookup", "classification": tt.class,
				"inboundAuth": "legacy", "inbound_auth": "legacy-snake",
				"inboundAuthAudience": tt.camel, "inbound_auth_audience": tt.snake,
				"endpoints": []any{map[string]any{"path": "/orders", "methods": []string{"GET"}}},
				"labels":    map[string]string{"owner": "commerce"},
			}
			before := maps.Clone(desired)
			a := &Adapter{Audience: tt.audience, Realms: []string{"sandbox"}, AllowUnauthenticatedREST: tt.allow}
			got, err := a.authenticatedContract(desired)
			if !reflect.DeepEqual(desired, before) {
				t.Fatal("authentication changed the caller's contract")
			}
			if tt.wantError != "" {
				if err == nil || !strings.Contains(err.Error(), tt.wantError) || got != nil {
					t.Fatalf("got contract=%v err=%v; want rejection %q", got, err, tt.wantError)
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			want := maps.Clone(before)
			for _, key := range []string{"inboundAuth", "inbound_auth", "inboundAuthAudience", "inbound_auth_audience"} {
				delete(want, key)
			}
			want["classification"] = strings.ToUpper(strings.TrimSpace(tt.class))
			if tt.wantAudience != "" {
				want["inboundAuth"] = "jwt"
				want["inboundAuthAudience"] = tt.wantAudience
			}
			if !reflect.DeepEqual(got, want) {
				t.Fatalf("got %#v; want %#v", got, want)
			}
			got["name"] = "changed"
			delete(got, "tenant_id")
			got["extra"] = true
			if !reflect.DeepEqual(desired, before) {
				t.Fatal("returned map aliases the caller's contract")
			}
		})
	}
}
