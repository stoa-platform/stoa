package adapters

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"reflect"
	"strings"
	"testing"
)

type contractTransport func(*http.Request) (*http.Response, error)

func (f contractTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }
func contractResponse(code int, body string) *http.Response {
	return &http.Response{StatusCode: code, Body: io.NopCloser(strings.NewReader(body)), Header: make(http.Header)}
}
func contractConfig(kind string) map[string]interface{} {
	switch kind {
	case "jwt", "jwt_validation":
		return map[string]interface{}{"issuer": "issuer-synthetic", "audience": "api", "jwks_url": "keys-synthetic", "required_claims": map[string]interface{}{"sub": "required"}}
	case "cors":
		return map[string]interface{}{"allowedOrigins": []interface{}{"origin-synthetic"}, "allowedMethods": []string{"GET"}, "allowedHeaders": []string{}, "exposeHeaders": []string{}, "maxAge": 9, "allowCredentials": false}
	case "rate_limit":
		return map[string]interface{}{"maxRequests": 7, "intervalSeconds": 9}
	case "logging":
		return map[string]interface{}{"logRequest": false, "logResponse": false}
	case "ip_filter":
		return map[string]interface{}{"mode": "deny", "ip_list": []string{"192.0.2.1"}}
	default:
		return map[string]interface{}{}
	}
}
func contractWM(t *testing.T, existing bool, writeCode int) (*WebMethodsAdapter, *int, *map[string]interface{}) {
	t.Helper()
	calls := 0
	var payload map[string]interface{}
	w := NewWebMethodsAdapter(AdapterConfig{})
	w.client = &http.Client{Transport: contractTransport(func(r *http.Request) (*http.Response, error) {
		calls++
		if r.Method == "GET" {
			if strings.HasSuffix(r.URL.Path, "/apis") {
				return contractResponse(200, `{"apiResponse":[{"id":"api-id","apiName":"api"}]}`), nil
			}
			if existing {
				return contractResponse(200, `{"policyActions":[{"id":"existing","templateKey":"jwtPolicy"}]}`), nil
			}
			return contractResponse(200, `{"policyActions":[]}`), nil
		}
		if existing && r.Method != "PUT" {
			t.Errorf("want update, got %s", r.Method)
		}
		if !existing && r.Method != "POST" {
			t.Errorf("want create, got %s", r.Method)
		}
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			t.Error(err)
		}
		return contractResponse(writeCode, `SYNTHETIC_BODY_TOKEN`), nil
	})}
	return w, &calls, &payload
}
func requireContractRefusal(t *testing.T, err error, calls int, code string) {
	t.Helper()
	if err == nil || calls != 0 {
		t.Fatalf("want local refusal without HTTP, got err=%v calls=%d", err, calls)
	}
	var coded interface{ PolicyErrorCode() string }
	if !errors.As(err, &coded) || coded.PolicyErrorCode() != code {
		t.Errorf("want typed %s, got %T %v", code, err, err)
	}
}

// T01: canonical and deprecated names have identical POST and PUT payloads.
func TestWebMethodsJWTValidationAliases(t *testing.T) {
	for _, existing := range []bool{false, true} {
		var previous map[string]interface{}
		for _, kind := range []string{"jwt", "jwt_validation"} {
			t.Run(fmt.Sprintf("%s/%t", kind, existing), func(t *testing.T) {
				w, _, payload := contractWM(t, existing, 201)
				if err := w.ApplyPolicy(context.Background(), "http://synthetic.invalid", "api", PolicyAction{Type: kind, Config: contractConfig(kind)}); err != nil {
					t.Fatal(err)
				}
				pa := (*payload)["policyAction"].(map[string]interface{})
				if pa["type"] != "jwtPolicy" {
					t.Errorf("untranslated type: %v", pa)
				}
				expected := map[string]interface{}{"jwtIssuer": "issuer-synthetic", "jwtAudience": "api", "jwksURL": "keys-synthetic", "requiredClaims": map[string]interface{}{"sub": "required"}}
				if !reflect.DeepEqual(pa["parameters"], expected) {
					t.Errorf("parameters: %v", pa["parameters"])
				}
				if previous != nil && !reflect.DeepEqual(previous, *payload) {
					t.Errorf("alias payload differs")
				}
				previous = *payload
			})
		}
	}
}

// T02/T03/T07: no native or arbitrary extension bypasses the STOA allowlist.
func TestWebMethodsPolicyCoverageContract(t *testing.T) {
	for _, kind := range []string{"cors", "rate_limit", "jwt_validation", "ip_filter", "logging", "caching", "transform", "", "unknown-policy-test", "jwt-validation", "corsPolicy", "throttlingPolicy", "logInvocationPolicy", "jwtPolicy", "ipFilterPolicy", "alias"} {
		t.Run(kind, func(t *testing.T) {
			w, calls, payload := contractWM(t, false, 201)
			err := w.ApplyPolicy(context.Background(), "http://synthetic.invalid", "api", PolicyAction{Type: kind, Config: contractConfig(kind)})
			mapped := map[string]string{"cors": "corsPolicy", "rate_limit": "throttlingPolicy", "jwt_validation": "jwtPolicy", "ip_filter": "ipFilterPolicy", "logging": "logInvocationPolicy"}
			if native, ok := mapped[kind]; ok {
				if err != nil {
					t.Fatal(err)
				}
				pa := (*payload)["policyAction"].(map[string]interface{})
				if pa["type"] != native {
					t.Errorf("payload %v", pa)
				}
				if kind == "logging" {
					params := pa["parameters"].(map[string]interface{})
					if params["logRequestPayload"] != false || params["logResponsePayload"] != false {
						t.Fatal("payload logging re-enabled")
					}
				}
			} else {
				code := "invalid"
				if kind == "caching" || kind == "transform" {
					code = "unsupported"
				}
				requireContractRefusal(t, err, *calls, code)
			}
		})
	}
}
func TestWebMethodsNativePolicyConfigContract(t *testing.T) {
	for kind, config := range map[string]map[string]interface{}{
		"jwtPolicy":        {"jwtIssuer": "SYNTHETIC", "jwtAudience": "api", "jwksURL": "keys", "requiredClaims": map[string]interface{}{"sub": "required"}},
		"throttlingPolicy": {"maxRequestCount": 7, "intervalInSeconds": 9}, "logInvocationPolicy": {"logRequestPayload": false, "logResponsePayload": false},
		"ipFilterPolicy": {"ipFilterMode": "DENY", "ipList": []string{"192.0.2.1"}}, "corsPolicy": contractConfig("cors"),
		"jwt_validation": {"issuer": "issuer", "jwtIssuer": "conflict", "audience": "api", "jwks_url": "keys"},
	} {
		t.Run(kind, func(t *testing.T) {
			w, calls, _ := contractWM(t, false, 201)
			err := w.ApplyPolicy(context.Background(), "http://synthetic.invalid", "api", PolicyAction{Type: kind, Config: config})
			requireContractRefusal(t, err, *calls, "invalid")
		})
	}
}

// T06: reject every invalid key/type/null/missing field before even a GET.
func TestWebMethodsPolicyInputConfigContract(t *testing.T) {
	cases := []struct {
		kind   string
		config map[string]interface{}
	}{
		{"rate_limit", map[string]interface{}{"requests_per_minute": 7}}, {"rate_limit", map[string]interface{}{"rpm": 7}},
		{"rate_limit", map[string]interface{}{"maxRequests": "7", "intervalSeconds": 9}}, {"rate_limit", map[string]interface{}{"maxRequests": nil, "intervalSeconds": 9}},
		{"rate_limit", map[string]interface{}{"maxRequests": 7}}, {"rate_limit", map[string]interface{}{"maxRequests": 7.5, "intervalSeconds": 9}},
		{"ip_filter", map[string]interface{}{"mode": "other", "ip_list": []string{}}}, {"ip_filter", map[string]interface{}{"mode": "deny", "ip_list": []interface{}{"192.0.2.1", nil}}},
		{"logging", map[string]interface{}{"logRequest": "false", "logResponse": false}}, {"logging", map[string]interface{}{"logRequest": nil, "logResponse": false}},
		{"cors", map[string]interface{}{"allowedOrigins": nil}}, {"cors", map[string]interface{}{"allowedOrigins": []interface{}{"origin", 4}}},
		{"jwt_validation", map[string]interface{}{"issuer": "issuer", "audience": "api"}},
	}
	for i, c := range cases {
		t.Run(fmt.Sprint(i), func(t *testing.T) {
			w, calls, _ := contractWM(t, false, 201)
			err := w.ApplyPolicy(context.Background(), "http://synthetic.invalid", "api", PolicyAction{Type: c.kind, Config: c.config})
			requireContractRefusal(t, err, *calls, "invalid")
		})
	}
}

// T05: an accepting Kong endpoint cannot make unsupported policy sync succeed.
func TestKongPolicyTranslationOrExplicitRefusal(t *testing.T) {
	for _, kind := range []string{"cors", "rate_limit", "jwt_validation", "ip_filter", "logging", "caching", "transform", "oidc_auth_server", "oidc_strategy", "oidc_scope"} {
		t.Run(kind, func(t *testing.T) {
			k := NewKongAdapter(AdapterConfig{})
			calls := 0
			k.client = &http.Client{Transport: contractTransport(func(r *http.Request) (*http.Response, error) { calls++; return contractResponse(201, `{}`), nil })}
			err := k.ApplyPolicy(context.Background(), "http://synthetic.invalid", "api", PolicyAction{Type: kind, Config: contractConfig(kind)})
			requireContractRefusal(t, err, calls, "unsupported")
		})
	}
}

// T04: public adapter errors retain HTTP status but never response or URL data.
func TestPolicyApplyDiagnosticsRedacted(t *testing.T) {
	for _, stage := range []string{"apply", "get", "transport", "oidc-upsert", "oidc-scope"} {
		t.Run(stage, func(t *testing.T) {
			w, _, _ := contractWM(t, false, 403)
			if stage != "apply" {
				w.client = &http.Client{Transport: contractTransport(func(r *http.Request) (*http.Response, error) {
					if stage == "transport" {
						return nil, fmt.Errorf("SYNTHETIC_TRANSPORT_TOKEN")
					}
					if stage != "get" && r.Method == "GET" {
						return contractResponse(200, `{}`), nil
					}
					return contractResponse(403, `SYNTHETIC_BODY_TOKEN Authorization: Bearer SYNTHETIC_TOKEN`), nil
				})}
			}
			var err error
			switch stage {
			case "oidc-upsert":
				err = w.UpsertAuthServer(context.Background(), "http://synthetic.invalid/?SYNTHETIC_URL_TOKEN", AuthServerSpec{Name: "api"})
			case "oidc-scope":
				err = w.UpsertScope(context.Background(), "http://synthetic.invalid/?SYNTHETIC_URL_TOKEN", ScopeSpec{})
			default:
				err = w.ApplyPolicy(context.Background(), "http://synthetic.invalid/SYNTHETIC_URL_TOKEN", "api", PolicyAction{Type: "logging", Config: contractConfig("logging")})
			}
			if err == nil {
				t.Fatal("expected failure")
			}
			for _, marker := range []string{"SYNTHETIC_", "synthetic.invalid", "Authorization"} {
				if strings.Contains(err.Error(), marker) {
					t.Errorf("diagnostic leaked marker: %v", err)
				}
			}
			if stage != "transport" && !strings.Contains(err.Error(), "403") {
				t.Errorf("missing HTTP code: %v", err)
			}
		})
	}
}

// Independently specified native values for the remaining supported types.
func TestWebMethodsNativeParametersContract(t *testing.T) {
	expected := map[string]map[string]interface{}{
		"rate_limit": {"maxRequestCount": 7, "intervalInSeconds": 9},
		"ip_filter":  {"ipFilterMode": "DENY", "ipList": []string{"192.0.2.1"}},
		"cors":       {"allowedOrigins": []string{"origin-synthetic"}, "allowedMethods": []string{"GET"}, "allowedHeaders": []string{}, "exposeHeaders": []string{}, "maxAge": 9, "allowCredentials": false},
	}
	for kind, params := range expected {
		t.Run(kind, func(t *testing.T) {
			w, _, payload := contractWM(t, false, 201)
			if err := w.ApplyPolicy(context.Background(), "http://synthetic.invalid", "api", PolicyAction{Type: kind, Config: contractConfig(kind)}); err != nil {
				t.Fatal(err)
			}
			want, _ := json.Marshal(params)
			got, _ := json.Marshal((*payload)["policyAction"].(map[string]interface{})["parameters"])
			if string(want) != string(got) {
				t.Errorf("parameters: got %s want %s", got, want)
			}
		})
	}
}
