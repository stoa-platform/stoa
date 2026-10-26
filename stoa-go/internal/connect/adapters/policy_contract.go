package adapters

import (
	"errors"
	"fmt"
	"math"
	"reflect"
)

// PolicyError contains only a contract code and an optional HTTP status.
// Never attach request URLs, configuration, names or upstream error text.
type PolicyError struct {
	Code       string
	HTTPStatus int
}

func (e *PolicyError) PolicyErrorCode() string { return e.Code }
func (e *PolicyError) Error() string {
	switch e.Code {
	case "invalid":
		return "invalid policy configuration or type"
	case "unsupported":
		return "unsupported policy"
	case "not_found":
		return "policy target not found"
	}
	if e.HTTPStatus > 0 {
		return fmt.Sprintf("policy request failed (HTTP %d)", e.HTTPStatus)
	}
	return "policy operation failed"
}

// SafePolicyError discards untrusted error strings, including transport URLs.
func SafePolicyError(err error) error {
	if err == nil {
		return nil
	}
	var e *PolicyError
	if errors.As(err, &e) {
		return &PolicyError{Code: e.Code, HTTPStatus: e.HTTPStatus}
	}
	return &PolicyError{}
}

type policyField struct {
	kind     string
	optional bool
	fallback interface{}
}

// policyConfigV1 is the single v1 configuration table. Fields are mandatory
// unless optional=true; fallback is then the documented value when absent.
// Explicit null (including typed nil) is always invalid. No key aliases exist.
// CORS retains its six historical optional defaults. required_claims is an
// optional string map. OIDC optional fields match the existing DTO dispatch;
// unsupported DTO fields are deliberately not accepted as policy config.
var policyConfigV1 = map[string]map[string]policyField{
	"cors": {
		"allowedOrigins":   {"strings", true, []interface{}{"*"}},
		"allowedMethods":   {"strings", true, []interface{}{"GET"}},
		"allowedHeaders":   {"strings", true, []interface{}{}},
		"exposeHeaders":    {"strings", true, []interface{}{}},
		"maxAge":           {"nonnegative", true, 3600},
		"allowCredentials": {"bool", true, false},
	},
	"rate_limit":       {"maxRequests": {"positive", false, nil}, "intervalSeconds": {"positive", false, nil}},
	"jwt_validation":   {"issuer": {"string", false, nil}, "audience": {"string", false, nil}, "jwks_url": {"string", false, nil}, "required_claims": {"claims", true, map[string]interface{}{}}},
	"ip_filter":        {"mode": {"mode", false, nil}, "ip_list": {"strings", false, nil}},
	"logging":          {"logRequest": {"bool", false, nil}, "logResponse": {"bool", false, nil}},
	"oidc_auth_server": {"discovery_url": {"string", false, nil}, "client_id": {"string", false, nil}, "client_secret": {"string", false, nil}, "scopes": {"strings", true, []interface{}{"openid"}}},
	"oidc_strategy":    {"auth_server_alias": {"string", false, nil}, "client_id": {"string", false, nil}, "audience": {"string", true, ""}},
	"oidc_scope":       {"scope_name": {"string", false, nil}, "audience": {"string", true, ""}, "auth_server_alias": {"string", false, nil}, "keycloak_scope": {"string", true, "openid"}},
	"caching":          {}, "transform": {},
}

// PreparePolicy is shared by the syncer (before dispatch) and direct adapter
// entry points. It returns a fresh config map and never mutates CP input.
// jwt is the sole deprecated type alias; native gateway types are not STOA.
func PreparePolicy(adapter GatewayAdapter, p PolicyAction) (PolicyAction, error) {
	if p.Type == "jwt" {
		p.Type = "jwt_validation"
	}
	fields, known := policyConfigV1[p.Type]
	if !known {
		return p, &PolicyError{Code: "invalid"}
	}
	switch adapter.(type) {
	case *KongAdapter, *GraviteeAdapter:
		return p, &PolicyError{Code: "unsupported"}
	}
	if p.Type == "caching" || p.Type == "transform" {
		return p, &PolicyError{Code: "unsupported"}
	}
	if p.Type == "oidc_auth_server" || p.Type == "oidc_strategy" || p.Type == "oidc_scope" {
		if _, ok := adapter.(OIDCAdapter); !ok {
			return p, &PolicyError{Code: "unsupported"}
		}
	}
	config := make(map[string]interface{}, len(fields))
	for key := range p.Config {
		if _, ok := fields[key]; !ok {
			return p, &PolicyError{Code: "invalid"}
		}
	}
	for key, field := range fields {
		value, present := p.Config[key]
		if !present {
			if !field.optional {
				return p, &PolicyError{Code: "invalid"}
			}
			value = field.fallback
		}
		if !validPolicyValue(value, field.kind) {
			return p, &PolicyError{Code: "invalid"}
		}
		config[key] = value
	}
	p.Config = config
	return p, nil
}
func validPolicyValue(value interface{}, kind string) bool {
	if value == nil {
		return false
	}
	v := reflect.ValueOf(value)
	switch v.Kind() {
	case reflect.Map, reflect.Slice, reflect.Ptr:
		if v.IsNil() {
			return false
		}
	}
	switch kind {
	case "string":
		_, ok := value.(string)
		return ok
	case "bool":
		_, ok := value.(bool)
		return ok
	case "mode":
		s, ok := value.(string)
		return ok && (s == "allow" || s == "deny" || s == "ALLOW" || s == "DENY")
	case "strings":
		switch list := value.(type) {
		case []string:
			return true
		case []interface{}:
			for _, item := range list {
				if _, ok := item.(string); !ok {
					return false
				}
			}
			return true
		}
		return false
	case "claims":
		claims, ok := value.(map[string]interface{})
		if !ok {
			return false
		}
		for _, item := range claims {
			if _, ok := item.(string); !ok {
				return false
			}
		}
		return true
	case "positive", "nonnegative":
		var n float64
		switch v.Kind() {
		case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
			n = float64(v.Int())
		case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
			n = float64(v.Uint())
		case reflect.Float64:
			n = v.Float()
		default:
			return false
		}
		minimum := 0.0
		if kind == "positive" {
			minimum = 1
		}
		return !math.IsNaN(n) && !math.IsInf(n, 0) && n >= minimum && n <= 9007199254740991 && math.Trunc(n) == n
	}
	return false
}

// policyValue is only a projection helper; public entry points validate first.
// Zero strings preserve the internal mapper's historical zero-value behavior.
func policyValue(config map[string]interface{}, kind, key string) interface{} {
	if value, ok := config[key]; ok {
		return value
	}
	field := policyConfigV1[kind][key]
	if field.optional {
		return field.fallback
	}
	if field.kind == "string" {
		return ""
	}
	return nil
}
