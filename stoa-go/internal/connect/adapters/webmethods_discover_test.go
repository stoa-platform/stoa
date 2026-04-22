package adapters

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestWebMethodsDiscover(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/rest/apigateway/apis":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{
						"id":         "api-wm-1",
						"apiName":    "Petstore",
						"apiVersion": "1.0.0",
						"isActive":   true,
						"type":       "REST",
					},
				},
			})
		case "/rest/apigateway/apis/api-wm-1":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": map[string]interface{}{
					"nativeEndpoint": []map[string]interface{}{
						{"uri": "http://petstore.example.com/v1"},
					},
					"resources": []map[string]interface{}{
						{
							"resourcePath": "/pets",
							"methods":      []string{"GET", "POST"},
						},
						{
							"resourcePath": "/pets/{id}",
							"methods":      []string{"GET", "DELETE"},
						},
					},
				},
			})
		case "/rest/apigateway/apis/api-wm-1/policyActions":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"policyActions": []map[string]interface{}{
					{
						"id":               "pa-1",
						"templateKey":      "throttlingAndMonitoring",
						"policyActionName": "rate-limit",
					},
				},
			})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "Administrator", Password: "manage"})
	apis, err := adapter.Discover(context.Background(), server.URL)
	if err != nil {
		t.Fatalf("discover error: %v", err)
	}
	if len(apis) != 1 {
		t.Fatalf("expected 1 API, got %d", len(apis))
	}

	api := apis[0]
	if api.Name != "Petstore" {
		t.Errorf("expected Petstore, got %s", api.Name)
	}
	if api.Version != "1.0.0" {
		t.Errorf("expected version 1.0.0, got %s", api.Version)
	}
	if !api.IsActive {
		t.Error("expected API to be active")
	}
	if api.BackendURL != "http://petstore.example.com/v1" {
		t.Errorf("unexpected backend URL: %s", api.BackendURL)
	}
	if len(api.Paths) != 2 {
		t.Errorf("expected 2 paths, got %d", len(api.Paths))
	}
	if len(api.Methods) != 4 {
		t.Errorf("expected 4 methods, got %d", len(api.Methods))
	}
	if len(api.Policies) != 1 || api.Policies[0] != "rate-limit" {
		t.Errorf("unexpected policies: %v", api.Policies)
	}
}

func TestWebMethodsDiscoverNestedResponse(t *testing.T) {
	// Real webMethods returns nested: {"apiResponse": [{"api": {...}, "responseStatus": "SUCCESS"}]}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/rest/apigateway/apis":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{
						"api": map[string]interface{}{
							"id": "api-nested-1", "apiName": "Petstore", "apiVersion": "1.0.0",
							"isActive": false, "type": "REST",
						},
						"responseStatus": "SUCCESS",
					},
					{
						"api": map[string]interface{}{
							"id": "api-nested-2", "apiName": "Payment Service", "apiVersion": "2.0.0",
							"isActive": true, "type": "REST",
						},
						"responseStatus": "SUCCESS",
					},
				},
			})
		case "/rest/apigateway/apis/api-nested-1":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": map[string]interface{}{
					"nativeEndpoint": []map[string]interface{}{{"uri": "https://petstore.example.com/v1"}},
					"resources":      []map[string]interface{}{{"resourcePath": "/pets", "methods": []string{"GET"}}},
				},
			})
		case "/rest/apigateway/apis/api-nested-2":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": map[string]interface{}{
					"nativeEndpoint": []map[string]interface{}{{"uri": "https://payments.internal.bank.com/v2"}},
					"resources":      []map[string]interface{}{{"resourcePath": "/transactions", "methods": []string{"GET", "POST"}}},
				},
			})
		default:
			// Return empty policyActions for any policy query
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"policyActions": []interface{}{}})
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "Administrator", Password: "manage"})
	apis, err := adapter.Discover(context.Background(), server.URL)
	if err != nil {
		t.Fatalf("discover nested error: %v", err)
	}
	if len(apis) != 2 {
		t.Fatalf("expected 2 APIs, got %d", len(apis))
	}
	if apis[0].Name != "Petstore" {
		t.Errorf("expected Petstore, got %s", apis[0].Name)
	}
	if apis[1].Name != "Payment Service" {
		t.Errorf("expected Payment Service, got %s", apis[1].Name)
	}
	if apis[1].BackendURL != "https://payments.internal.bank.com/v2" {
		t.Errorf("unexpected backend URL: %s", apis[1].BackendURL)
	}
}

func TestWebMethodsDiscoverWithBasicAuth(t *testing.T) {
	var receivedUser, receivedPass string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedUser, receivedPass, _ = r.BasicAuth()
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"apiResponse": []interface{}{}})
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "pass123"})
	_, _ = adapter.Discover(context.Background(), server.URL)

	if receivedUser != "admin" || receivedPass != "pass123" {
		t.Errorf("expected basic auth admin:pass123, got %s:%s", receivedUser, receivedPass)
	}
}
