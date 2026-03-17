package adapters

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestWebMethodsDetect(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/rest/apigateway/health" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "Administrator", Password: "manage"})
	ok, err := adapter.Detect(context.Background(), server.URL)
	if err != nil {
		t.Fatalf("detect error: %v", err)
	}
	if !ok {
		t.Error("expected webMethods to be detected")
	}
}

func TestWebMethodsDetectNotWebMethods(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	ok, err := adapter.Detect(context.Background(), server.URL)
	if err != nil {
		t.Fatalf("detect error: %v", err)
	}
	if ok {
		t.Error("expected webMethods NOT to be detected")
	}
}

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
