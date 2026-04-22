package adapters

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestWebMethodsUpsertAlias(t *testing.T) {
	server := wmMockServer(t, nil, nil)
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	err := adapter.UpsertAlias(context.Background(), server.URL, AliasSpec{
		Name: "backend-petstore", EndpointURI: "https://petstore.example.com/v1",
	})
	if err != nil {
		t.Fatalf("upsert alias error: %v", err)
	}
}

func TestWebMethodsUpsertAliasIdempotent(t *testing.T) {
	var methodUsed string
	existing := []wmAlias{{ID: "alias-ep-1", Name: "backend-petstore", Type: "endpoint"}}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/alias" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"alias": existing})
		case r.URL.Path == "/rest/apigateway/alias/alias-ep-1" && r.Method == http.MethodPut:
			methodUsed = "PUT"
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	err := adapter.UpsertAlias(context.Background(), server.URL, AliasSpec{
		Name: "backend-petstore", EndpointURI: "https://petstore.example.com/v2",
	})
	if err != nil {
		t.Fatalf("upsert alias error: %v", err)
	}
	if methodUsed != "PUT" {
		t.Errorf("expected PUT for existing alias, got %s", methodUsed)
	}
}
