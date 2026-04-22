package adapters

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// wmMockServer is shared with webmethods_alias_test.go (same package).
func wmMockServer(t *testing.T, aliases []wmAlias, strategies []wmStrategy) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/alias" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"alias": aliases})
		case r.URL.Path == "/rest/apigateway/alias" && r.Method == http.MethodPost:
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"alias": map[string]string{"id": "new-alias-1"}})
		case strings.HasPrefix(r.URL.Path, "/rest/apigateway/alias/") && r.Method == http.MethodPut:
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{})
		case strings.HasPrefix(r.URL.Path, "/rest/apigateway/alias/") && r.Method == http.MethodDelete:
			w.WriteHeader(http.StatusOK)
		case r.URL.Path == "/rest/apigateway/strategies" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"strategy": strategies})
		case r.URL.Path == "/rest/apigateway/strategies" && r.Method == http.MethodPost:
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"strategy": map[string]string{"id": "new-strat-1"}})
		case strings.HasPrefix(r.URL.Path, "/rest/apigateway/strategies/") && r.Method == http.MethodPut:
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{})
		case r.URL.Path == "/rest/apigateway/scopes" && r.Method == http.MethodPost:
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
}

func TestWebMethodsUpsertAuthServer(t *testing.T) {
	server := wmMockServer(t, nil, nil)
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	err := adapter.UpsertAuthServer(context.Background(), server.URL, AuthServerSpec{
		Name:         "KeycloakOIDC",
		DiscoveryURL: "https://auth.example.com/realms/stoa/.well-known/openid-configuration",
		ClientID:     "stoa-gateway",
		ClientSecret: "secret",
		Scopes:       []string{"openid", "profile"},
	})
	if err != nil {
		t.Fatalf("upsert auth server error: %v", err)
	}
}

func TestWebMethodsUpsertAuthServerIdempotent(t *testing.T) {
	var methodUsed string
	existing := []wmAlias{{ID: "alias-kc-1", Name: "KeycloakOIDC", Type: "authServerAlias"}}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/alias" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"alias": existing})
		case r.URL.Path == "/rest/apigateway/alias/alias-kc-1" && r.Method == http.MethodPut:
			methodUsed = "PUT"
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	err := adapter.UpsertAuthServer(context.Background(), server.URL, AuthServerSpec{
		Name: "KeycloakOIDC", DiscoveryURL: "https://auth.example.com/.well-known/openid-configuration", ClientID: "stoa-gateway",
	})
	if err != nil {
		t.Fatalf("upsert auth server error: %v", err)
	}
	if methodUsed != "PUT" {
		t.Errorf("expected PUT for existing auth server, got %s", methodUsed)
	}
}

func TestWebMethodsUpsertStrategy(t *testing.T) {
	server := wmMockServer(t, nil, nil)
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	err := adapter.UpsertStrategy(context.Background(), server.URL, StrategySpec{
		Name: "stoa-oauth2", AuthServerAlias: "KeycloakOIDC", Audience: "",
	})
	if err != nil {
		t.Fatalf("upsert strategy error: %v", err)
	}
}

func TestWebMethodsUpsertScope(t *testing.T) {
	server := wmMockServer(t, nil, nil)
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	err := adapter.UpsertScope(context.Background(), server.URL, ScopeSpec{
		ScopeName: "KeycloakOIDC:openid", Audience: "", AuthServerAlias: "KeycloakOIDC", KeycloakScope: "openid",
	})
	if err != nil {
		t.Fatalf("upsert scope error: %v", err)
	}
}

func TestWebMethodsUpsertScopeEmptyAudience(t *testing.T) {
	var receivedPayload map[string]interface{}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path == "/rest/apigateway/scopes" && r.Method == http.MethodPost {
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &receivedPayload)
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	err := adapter.UpsertScope(context.Background(), server.URL, ScopeSpec{
		ScopeName: "KeycloakOIDC:openid", Audience: "", AuthServerAlias: "KeycloakOIDC",
	})
	if err != nil {
		t.Fatalf("upsert scope error: %v", err)
	}
	audience, ok := receivedPayload["audience"]
	if !ok {
		t.Fatal("audience field missing from payload — must be present as empty string")
	}
	if audience != "" {
		t.Errorf("expected empty audience, got %v", audience)
	}
}

func TestWebMethodsOIDCFullFlow(t *testing.T) {
	var calls []string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/alias" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"alias": []interface{}{}})
		case r.URL.Path == "/rest/apigateway/alias" && r.Method == http.MethodPost:
			calls = append(calls, "create-auth-server")
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"alias": map[string]string{"id": "alias-new"}})
		case r.URL.Path == "/rest/apigateway/strategies" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"strategy": []interface{}{}})
		case r.URL.Path == "/rest/apigateway/strategies" && r.Method == http.MethodPost:
			calls = append(calls, "create-strategy")
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"strategy": map[string]string{"id": "strat-new"}})
		case r.URL.Path == "/rest/apigateway/scopes" && r.Method == http.MethodPost:
			calls = append(calls, "create-scope")
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})

	if err := adapter.UpsertAuthServer(context.Background(), server.URL, AuthServerSpec{
		Name: "KeycloakOIDC", DiscoveryURL: "https://auth.example.com/.well-known/openid-configuration", ClientID: "stoa-gateway",
	}); err != nil {
		t.Fatalf("auth server error: %v", err)
	}
	if err := adapter.UpsertStrategy(context.Background(), server.URL, StrategySpec{
		Name: "stoa-oauth2", AuthServerAlias: "KeycloakOIDC", Audience: "",
	}); err != nil {
		t.Fatalf("strategy error: %v", err)
	}
	if err := adapter.UpsertScope(context.Background(), server.URL, ScopeSpec{
		ScopeName: "KeycloakOIDC:openid", Audience: "", AuthServerAlias: "KeycloakOIDC",
	}); err != nil {
		t.Fatalf("scope error: %v", err)
	}

	expected := []string{"create-auth-server", "create-strategy", "create-scope"}
	if len(calls) != 3 {
		t.Fatalf("expected 3 calls, got %d: %v", len(calls), calls)
	}
	for i, exp := range expected {
		if calls[i] != exp {
			t.Errorf("call %d: expected %s, got %s", i, exp, calls[i])
		}
	}
}
