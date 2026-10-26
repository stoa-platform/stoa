package connect

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// regression for CAB-2280
func TestPolicySyncerJWTValidationAliases(t *testing.T) {
	for _, kind := range []string{"jwt", "jwt_validation"} {
		t.Run(kind, func(t *testing.T) {
			var payload map[string]interface{}
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method == "GET" {
					if strings.HasSuffix(r.URL.Path, "/apis") {
						if _, err := io.WriteString(w, `{"apiResponse":[{"id":"id","apiName":"api"}]}`); err != nil {
							t.Errorf("write response: %v", err)
						}
					} else {
						if _, err := io.WriteString(w, `{"policyActions":[]}`); err != nil {
							t.Errorf("write response: %v", err)
						}
					}
					return
				}
				if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
					t.Errorf("decode request: %v", err)
					http.Error(w, "invalid request", http.StatusBadRequest)
					return
				}
				w.WriteHeader(201)
			}))
			defer server.Close()
			s := newPolicySyncer(adapters.NewWebMethodsAdapter(adapters.AdapterConfig{}))
			result := s.SyncPolicies(context.Background(), server.URL, []PendingPolicy{{ID: "p", Name: "api", PolicyType: kind, Enabled: true, Config: map[string]interface{}{"issuer": "issuer", "audience": "api", "jwks_url": "keys"}}})[0]
			if result.Status != "applied" {
				t.Fatal(result)
			}
			pa := payload["policyAction"].(map[string]interface{})
			if pa["type"] != "jwtPolicy" {
				t.Errorf("untranslated: %v", pa)
			}
		})
	}
}

// regression for CAB-2280
func TestPolicySyncerOIDCUnsupportedExplicitRefusal(t *testing.T) {
	for _, kind := range []string{"oidc_auth_server", "oidc_strategy", "oidc_scope"} {
		m := &policyMock{}
		result := newPolicySyncer(m).SyncPolicies(context.Background(), "http://synthetic.invalid", []PendingPolicy{{ID: "p", Name: "api", PolicyType: kind, Enabled: true}})[0]
		if result.Status != "failed" || !strings.Contains(result.Error, "unsupported") || len(m.applied) != 0 {
			t.Errorf("%s: result=%+v calls=%v", kind, result, m.applied)
		}
	}
}

// T07: alias is outside the authoritative STOA type set, with or without OIDC.
// regression for CAB-2280
func TestPolicySyncerAliasTranslationOrRefusal(t *testing.T) {
	for _, a := range []adapters.GatewayAdapter{&policyMock{}, &policyMockOIDC{}} {
		result := newPolicySyncer(a).SyncPolicies(context.Background(), "http://synthetic.invalid", []PendingPolicy{{ID: "p", Name: "api", PolicyType: "alias", Enabled: true}})[0]
		if result.Status != "failed" {
			t.Errorf("alias unexpectedly applied: %+v", result)
		}
	}
}

// regression for CAB-2280
func TestPolicySyncDiagnosticsRedacted(t *testing.T) {
	var logs bytes.Buffer
	old := log.Writer()
	log.SetOutput(&logs)
	defer log.SetOutput(old)
	m := &policyMock{applyErr: errors.New("SYNTHETIC_BODY_TOKEN http://synthetic.invalid/?SYNTHETIC_URL_TOKEN")}
	result := newPolicySyncer(m).SyncPolicies(context.Background(), "http://synthetic.invalid", []PendingPolicy{{ID: "p", Name: "api\nSYNTHETIC_NAME_TOKEN", PolicyType: "logging", Enabled: true, Config: map[string]interface{}{"logRequest": false, "logResponse": false}}})[0]
	if result.Status != "failed" {
		t.Fatal(result)
	}
	var ack string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		ack = string(b)
		w.WriteHeader(204)
	}))
	defer server.Close()
	c := newCPClient(server.URL, "synthetic-test-token", http.DefaultTransport)
	if err := c.ReportSyncAck(context.Background(), "gateway", SyncAckPayload{SyncedPolicies: []SyncedPolicyResult{result}}); err != nil {
		t.Fatal(err)
	}
	for surface, value := range map[string]string{"result": result.Error, "logs": logs.String(), "ack": ack} {
		if strings.Contains(value, "SYNTHETIC_") || strings.Contains(value, "synthetic.invalid") {
			t.Errorf("%s leaked diagnostic: %s", surface, value)
		}
	}
}

// regression for CAB-2280
func TestPolicySyncerRejectsInvalidConfigBeforeDispatch(t *testing.T) {
	for _, kind := range []string{"cors", "rate_limit", "jwt_validation", "ip_filter", "logging", "oidc_auth_server", "oidc_strategy", "oidc_scope"} {
		t.Run(kind, func(t *testing.T) {
			m := &policyMockOIDC{}
			result := newPolicySyncer(m).SyncPolicies(context.Background(), "http://synthetic.invalid", []PendingPolicy{{ID: "p", Name: "api", PolicyType: kind, Enabled: true, Config: map[string]interface{}{"SYNTHETIC_UNKNOWN_KEY": "SYNTHETIC_CONFIG_VALUE"}}})[0]
			if result.Status != "failed" || len(m.applied)+len(m.authServerSpecs)+len(m.strategySpecs)+len(m.scopeSpecs) != 0 {
				t.Fatalf("invalid input dispatched: %+v %+v", result, m)
			}
			if strings.Contains(result.Error, "SYNTHETIC_") {
				t.Fatal("config leaked")
			}
		})
	}
}

// regression for CAB-2280
func TestPolicySyncerRealAdaptersRefuseLocally(t *testing.T) {
	for name, a := range map[string]adapters.GatewayAdapter{"kong": adapters.NewKongAdapter(adapters.AdapterConfig{}), "gravitee": adapters.NewGraviteeAdapter(adapters.AdapterConfig{})} {
		for _, kind := range []string{"cors", "rate_limit", "jwt_validation", "ip_filter", "logging", "caching", "transform", "oidc_auth_server", "oidc_strategy", "oidc_scope"} {
			t.Run(name+"/"+kind, func(t *testing.T) {
				calls := 0
				server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { calls++; w.WriteHeader(201) }))
				defer server.Close()
				result := newPolicySyncer(a).SyncPolicies(context.Background(), server.URL, []PendingPolicy{{ID: "p", Name: "api", PolicyType: kind, Enabled: true}})[0]
				if result.Status != "failed" || !strings.Contains(result.Error, "unsupported") || calls != 0 {
					t.Fatalf("result=%+v HTTP=%d", result, calls)
				}
			})
		}
	}
}

// Explicit empty values are preserved; only absent optional fields get defaults.
// regression for CAB-2280
func TestPolicyOIDCExplicitEmptyValuesContract(t *testing.T) {
	for _, kind := range []string{"oidc_auth_server", "oidc_scope"} {
		t.Run(kind, func(t *testing.T) {
			var payload map[string]interface{}
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method == "GET" {
					if _, err := io.WriteString(w, `{}`); err != nil {
						t.Errorf("write response: %v", err)
					}
					return
				}
				if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
					t.Errorf("decode request: %v", err)
					http.Error(w, "invalid request", http.StatusBadRequest)
					return
				}
				w.WriteHeader(201)
			}))
			defer server.Close()
			config := map[string]interface{}{"scope_name": "scope", "auth_server_alias": "idp", "audience": "", "keycloak_scope": ""}
			if kind == "oidc_auth_server" {
				config = map[string]interface{}{"discovery_url": "discovery", "client_id": "client", "client_secret": "synthetic", "scopes": []interface{}{}}
			}
			result := newPolicySyncer(adapters.NewWebMethodsAdapter(adapters.AdapterConfig{})).SyncPolicies(context.Background(), server.URL, []PendingPolicy{{ID: "p", Name: "api", PolicyType: kind, Enabled: true, Config: config}})[0]
			if result.Status != "applied" {
				t.Fatal(result)
			}
			if kind == "oidc_auth_server" {
				scopes, ok := payload["scopes"].([]interface{})
				if !ok || len(scopes) != 0 {
					t.Errorf("explicit empty scopes changed: %v", payload)
				}
			} else if payload["keycloakScope"] != "" {
				t.Errorf("explicit empty keycloak_scope changed: %v", payload)
			}
		})
	}
}

// regression for CAB-2280
func TestPolicyHTTPDiagnosticsThroughAckContract(t *testing.T) {
	for _, kind := range []string{"logging", "oidc_auth_server", "oidc_strategy", "oidc_scope"} {
		t.Run(kind, func(t *testing.T) {
			var logs bytes.Buffer
			old := log.Writer()
			log.SetOutput(&logs)
			defer log.SetOutput(old)
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method == "GET" {
					if strings.HasSuffix(r.URL.Path, "/apis") {
						if _, err := io.WriteString(w, `{"apiResponse":[{"id":"id","apiName":"api\nSYNTHETIC_NAME_TOKEN"}]}`); err != nil {
							t.Errorf("write response: %v", err)
						}
					} else {
						if _, err := io.WriteString(w, `{}`); err != nil {
							t.Errorf("write response: %v", err)
						}
					}
					return
				}
				w.WriteHeader(403)
				if _, err := io.WriteString(w, `SYNTHETIC_BODY_TOKEN Authorization: Bearer SYNTHETIC_CONFIG_TOKEN`); err != nil {
					t.Errorf("write response: %v", err)
				}
			}))
			defer server.Close()
			configs := map[string]map[string]interface{}{
				"logging":          {"logRequest": false, "logResponse": false},
				"oidc_auth_server": {"discovery_url": "discovery", "client_id": "client", "client_secret": "SYNTHETIC_CONFIG_TOKEN"},
				"oidc_strategy":    {"auth_server_alias": "idp", "client_id": "client"},
				"oidc_scope":       {"scope_name": "scope", "auth_server_alias": "idp"},
			}
			result := newPolicySyncer(adapters.NewWebMethodsAdapter(adapters.AdapterConfig{})).SyncPolicies(context.Background(), server.URL, []PendingPolicy{{ID: "p", Name: "api\nSYNTHETIC_NAME_TOKEN", PolicyType: kind, Enabled: true, Config: configs[kind]}})[0]
			if result.Status != "failed" || !strings.Contains(result.Error, "403") {
				t.Fatalf("want failed with HTTP code: %+v", result)
			}
			var ack string
			cp := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				b, _ := io.ReadAll(r.Body)
				ack = string(b)
				w.WriteHeader(403)
				if _, err := io.WriteString(w, "SYNTHETIC_ACK_TOKEN"); err != nil {
					t.Errorf("write response: %v", err)
				}
			}))
			defer cp.Close()
			err := newCPClient(cp.URL, "synthetic-test-token", http.DefaultTransport).ReportSyncAck(context.Background(), "gateway", SyncAckPayload{SyncedPolicies: []SyncedPolicyResult{result}})
			if err == nil || !strings.Contains(err.Error(), "403") {
				t.Fatalf("missing ack status: %v", err)
			}
			for surface, value := range map[string]string{"result": result.Error, "logs": logs.String(), "ack": ack, "ack-error": err.Error()} {
				if strings.Contains(value, "SYNTHETIC_") || strings.Contains(value, server.URL) {
					t.Errorf("%s leaked: %s", surface, value)
				}
			}
		})
	}
}
