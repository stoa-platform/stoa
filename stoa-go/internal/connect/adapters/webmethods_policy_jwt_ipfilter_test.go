// regression for CAB-1944 (GO-1 audit H.4, tracked in CAB-2161): jwtPolicy
// and ipFilterPolicy STOA → webMethods parameter mapping. Pre-fix, both
// types fell through to the default passthrough, sending raw STOA config
// to webMethods which rejected with 400. Field names below are committed
// under WM-10.15-HYPOTHESIS and must be validated in staging before the
// BDF demo — ticket CAB-2161.
package adapters

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
)

// TestMapPolicyConfig_JwtPolicy — STOA-shaped jwt config is mapped to the
// webMethods-expected field names (jwtIssuer, jwtAudience, jwksURL,
// requiredClaims).
func TestMapPolicyConfig_JwtPolicy(t *testing.T) {
	result := mapPolicyConfig("jwtPolicy", map[string]interface{}{
		"issuer":          "https://keycloak.gostoa.dev/realms/oasis",
		"audience":        "stoa-portal",
		"jwks_url":        "https://keycloak.gostoa.dev/realms/oasis/protocol/openid-connect/certs",
		"required_claims": map[string]interface{}{"sub": "required"},
	})

	if result["jwtIssuer"] != "https://keycloak.gostoa.dev/realms/oasis" {
		t.Errorf("jwtIssuer: got %v", result["jwtIssuer"])
	}
	if result["jwtAudience"] != "stoa-portal" {
		t.Errorf("jwtAudience: got %v", result["jwtAudience"])
	}
	if result["jwksURL"] != "https://keycloak.gostoa.dev/realms/oasis/protocol/openid-connect/certs" {
		t.Errorf("jwksURL: got %v", result["jwksURL"])
	}
	claims, ok := result["requiredClaims"].(map[string]interface{})
	if !ok || claims["sub"] != "required" {
		t.Errorf("requiredClaims: got %v", result["requiredClaims"])
	}
}

// TestMapPolicyConfig_JwtPolicyDefaults — missing STOA fields fall back to
// safe defaults (empty strings / empty map) rather than nil, so the
// webMethods payload always has every field present.
func TestMapPolicyConfig_JwtPolicyDefaults(t *testing.T) {
	result := mapPolicyConfig("jwtPolicy", map[string]interface{}{})
	for _, key := range []string{"jwtIssuer", "jwtAudience", "jwksURL"} {
		if result[key] != "" {
			t.Errorf("%s should default to empty string, got %v", key, result[key])
		}
	}
	if _, ok := result["requiredClaims"].(map[string]interface{}); !ok {
		t.Errorf("requiredClaims default should be map, got %T", result["requiredClaims"])
	}
}

// TestMapPolicyConfig_IpFilterPolicy — mode is uppercased, ip_list is
// renamed to ipList.
func TestMapPolicyConfig_IpFilterPolicy(t *testing.T) {
	result := mapPolicyConfig("ipFilterPolicy", map[string]interface{}{
		"mode":    "allow",
		"ip_list": []interface{}{"10.0.0.0/8", "192.168.1.1"},
	})

	if result["ipFilterMode"] != "ALLOW" {
		t.Errorf("ipFilterMode: got %v, want ALLOW", result["ipFilterMode"])
	}
	list, ok := result["ipList"].([]interface{})
	if !ok || len(list) != 2 {
		t.Fatalf("ipList: got %v", result["ipList"])
	}
	if list[0] != "10.0.0.0/8" || list[1] != "192.168.1.1" {
		t.Errorf("ipList contents: got %v", list)
	}
}

// TestMapPolicyConfig_IpFilterPolicy_DenyMode — deny mode also uppercases.
func TestMapPolicyConfig_IpFilterPolicy_DenyMode(t *testing.T) {
	result := mapPolicyConfig("ipFilterPolicy", map[string]interface{}{
		"mode":    "deny",
		"ip_list": []interface{}{"1.2.3.4"},
	})
	if result["ipFilterMode"] != "DENY" {
		t.Errorf("ipFilterMode: got %v, want DENY", result["ipFilterMode"])
	}
}

// TestMapPolicyConfig_UnknownTypePassthrough — baseline: types that are
// neither in the mapping nor in the switch fall through unchanged. Proves
// the jwt/ipFilter cases didn't break the fallback contract used by
// custom gateway-specific policies.
func TestMapPolicyConfig_UnknownTypePassthrough(t *testing.T) {
	in := map[string]interface{}{"custom": "value", "n": 42}
	result := mapPolicyConfig("someCustomType", in)
	if result["custom"] != "value" || result["n"] != 42 {
		t.Errorf("passthrough broken: %v", result)
	}
}

// TestApplyPolicy_JwtEndToEnd — full path: ApplyPolicy(type=jwt) resolves
// the API, discovers no existing policy (POST path), and sends a payload
// whose `type` is the mapped wM name and whose `parameters` are the mapped
// field names. Proves the H.4 wiring reaches the HTTP layer as expected.
func TestApplyPolicy_JwtEndToEnd(t *testing.T) {
	var receivedPayload map[string]interface{}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "api-secured", "apiName": "Petstore", "apiVersion": "1.0", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/api-secured/policyActions" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"policyActions": []interface{}{}})
		case r.URL.Path == "/rest/apigateway/policyActions" && r.Method == http.MethodPost:
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &receivedPayload)
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"policyAction": map[string]interface{}{"id": "pa-jwt-1"}})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	err := adapter.ApplyPolicy(context.Background(), server.URL, "Petstore", PolicyAction{
		Type: "jwt",
		Config: map[string]interface{}{
			"issuer":   "https://kc/realms/oasis",
			"audience": "stoa-portal",
			"jwks_url": "https://kc/realms/oasis/certs",
		},
	})
	if err != nil {
		t.Fatalf("apply policy error: %v", err)
	}

	pa, ok := receivedPayload["policyAction"].(map[string]interface{})
	if !ok {
		t.Fatal("missing policyAction in payload")
	}
	if pa["type"] != "jwtPolicy" {
		t.Errorf("expected type jwtPolicy, got %v", pa["type"])
	}
	params, ok := pa["parameters"].(map[string]interface{})
	if !ok {
		t.Fatal("missing parameters")
	}
	if params["jwtIssuer"] != "https://kc/realms/oasis" {
		t.Errorf("jwtIssuer not mapped: %v", params["jwtIssuer"])
	}
	if params["jwtAudience"] != "stoa-portal" {
		t.Errorf("jwtAudience not mapped: %v", params["jwtAudience"])
	}
	if params["jwksURL"] != "https://kc/realms/oasis/certs" {
		t.Errorf("jwksURL not mapped: %v", params["jwksURL"])
	}
}

// TestApplyPolicy_IpFilterEndToEnd — same end-to-end proof for ipFilter:
// type is ipFilterPolicy, parameters are ipFilterMode + ipList.
func TestApplyPolicy_IpFilterEndToEnd(t *testing.T) {
	var receivedPayload map[string]interface{}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "api-iplock", "apiName": "Internal", "apiVersion": "1.0", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/api-iplock/policyActions" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"policyActions": []interface{}{}})
		case r.URL.Path == "/rest/apigateway/policyActions" && r.Method == http.MethodPost:
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &receivedPayload)
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"policyAction": map[string]interface{}{"id": "pa-ipf-1"}})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	err := adapter.ApplyPolicy(context.Background(), server.URL, "Internal", PolicyAction{
		Type: "ip_filter",
		Config: map[string]interface{}{
			"mode":    "allow",
			"ip_list": []interface{}{"10.0.0.0/8"},
		},
	})
	if err != nil {
		t.Fatalf("apply policy error: %v", err)
	}

	pa := receivedPayload["policyAction"].(map[string]interface{})
	if pa["type"] != "ipFilterPolicy" {
		t.Errorf("expected type ipFilterPolicy, got %v", pa["type"])
	}
	params := pa["parameters"].(map[string]interface{})
	if params["ipFilterMode"] != "ALLOW" {
		t.Errorf("ipFilterMode: got %v", params["ipFilterMode"])
	}
	list, ok := params["ipList"].([]interface{})
	if !ok || len(list) != 1 || list[0] != "10.0.0.0/8" {
		t.Errorf("ipList: got %v", params["ipList"])
	}
}
