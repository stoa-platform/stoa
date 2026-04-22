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

func TestWebMethodsApplyPolicy(t *testing.T) {
	var receivedPath string
	var receivedPayload map[string]interface{}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "api-123", "apiName": "Petstore", "apiVersion": "1.0", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/api-123/policyActions" && r.Method == http.MethodGet:
			// No existing policies — triggers POST (create)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"policyActions": []interface{}{}})
		case r.URL.Path == "/rest/apigateway/policyActions" && r.Method == http.MethodPost:
			receivedPath = r.URL.Path
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &receivedPayload)
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"policyAction": map[string]interface{}{"id": "pa-new-1"},
			})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "Administrator", Password: "manage"})
	err := adapter.ApplyPolicy(context.Background(), server.URL, "Petstore", PolicyAction{
		Type:   "rate_limit",
		Config: map[string]interface{}{"maxRequests": 200, "intervalSeconds": 30},
	})
	if err != nil {
		t.Fatalf("apply policy error: %v", err)
	}
	if receivedPath != "/rest/apigateway/policyActions" {
		t.Errorf("unexpected path: %s", receivedPath)
	}

	pa, ok := receivedPayload["policyAction"].(map[string]interface{})
	if !ok {
		t.Fatal("missing policyAction in payload")
	}
	if pa["type"] != "throttlingPolicy" {
		t.Errorf("expected throttlingPolicy, got %v", pa["type"])
	}
	params, ok := pa["parameters"].(map[string]interface{})
	if !ok {
		t.Fatal("missing parameters")
	}
	if params["maxRequestCount"] != float64(200) {
		t.Errorf("expected maxRequestCount=200, got %v", params["maxRequestCount"])
	}
	if params["intervalInSeconds"] != float64(30) {
		t.Errorf("expected intervalInSeconds=30, got %v", params["intervalInSeconds"])
	}
	if receivedPayload["apiId"] != "api-123" {
		t.Errorf("expected apiId=api-123, got %v", receivedPayload["apiId"])
	}
}

func TestWebMethodsApplyPolicyAPINotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"apiResponse": []map[string]interface{}{}})
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	err := adapter.ApplyPolicy(context.Background(), server.URL, "NonExistent", PolicyAction{
		Type: "cors", Config: map[string]interface{}{},
	})
	if err == nil {
		t.Fatal("expected error for non-existent API")
	}
	if !strings.Contains(err.Error(), "not found") {
		t.Errorf("expected 'not found' error, got: %v", err)
	}
}

func TestWebMethodsApplyPolicyCORS(t *testing.T) {
	var receivedPayload map[string]interface{}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "api-cors", "apiName": "MyAPI", "apiVersion": "2.0", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/api-cors/policyActions" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"policyActions": []interface{}{}})
		case r.URL.Path == "/rest/apigateway/policyActions" && r.Method == http.MethodPost:
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &receivedPayload)
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "admin"})
	err := adapter.ApplyPolicy(context.Background(), server.URL, "MyAPI", PolicyAction{
		Type: "cors",
		Config: map[string]interface{}{
			"allowedOrigins": []string{"https://example.com"},
			"allowedMethods": []string{"GET", "POST"},
			"maxAge":         7200,
		},
	})
	if err != nil {
		t.Fatalf("apply CORS policy error: %v", err)
	}

	pa := receivedPayload["policyAction"].(map[string]interface{})
	if pa["type"] != "corsPolicy" {
		t.Errorf("expected corsPolicy, got %v", pa["type"])
	}
}

func TestWebMethodsApplyPolicyIdempotent(t *testing.T) {
	var method string
	var requestPath string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "api-upsert", "apiName": "Petstore", "apiVersion": "1.0", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/api-upsert/policyActions" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"policyActions": []map[string]interface{}{
					{"id": "pa-existing", "templateKey": "throttlingPolicy", "policyActionName": "stoa-Petstore-rate_limit"},
				},
			})
		case strings.HasPrefix(r.URL.Path, "/rest/apigateway/policyActions"):
			method = r.Method
			requestPath = r.URL.Path
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"policyAction": map[string]interface{}{"id": "pa-existing"}})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	err := adapter.ApplyPolicy(context.Background(), server.URL, "Petstore", PolicyAction{
		Type:   "rate_limit",
		Config: map[string]interface{}{"maxRequests": 500, "intervalSeconds": 60},
	})
	if err != nil {
		t.Fatalf("apply policy error: %v", err)
	}
	if method != http.MethodPut {
		t.Errorf("expected PUT (update existing), got %s", method)
	}
	if requestPath != "/rest/apigateway/policyActions/pa-existing" {
		t.Errorf("expected PUT to pa-existing, got %s", requestPath)
	}
}

func TestWebMethodsRemovePolicy(t *testing.T) {
	var deletedPath string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "api-rm-1", "apiName": "Petstore", "apiVersion": "1.0", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/api-rm-1/policyActions" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"policyActions": []map[string]interface{}{
					{"id": "pa-to-delete", "templateKey": "throttlingPolicy", "policyActionName": "rate-limit"},
					{"id": "pa-keep", "templateKey": "corsPolicy", "policyActionName": "cors"},
				},
			})
		case strings.HasPrefix(r.URL.Path, "/rest/apigateway/policyActions/") && r.Method == http.MethodDelete:
			deletedPath = r.URL.Path
			w.WriteHeader(http.StatusOK)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "Administrator", Password: "manage"})
	err := adapter.RemovePolicy(context.Background(), server.URL, "Petstore", "rate_limit")
	if err != nil {
		t.Fatalf("remove policy error: %v", err)
	}
	if deletedPath != "/rest/apigateway/policyActions/pa-to-delete" {
		t.Errorf("expected delete of pa-to-delete, got path: %s", deletedPath)
	}
}

func TestWebMethodsRemovePolicyNotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "api-rm-2", "apiName": "Petstore", "apiVersion": "1.0", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/api-rm-2/policyActions" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"policyActions": []map[string]interface{}{
					{"id": "pa-1", "templateKey": "corsPolicy", "policyActionName": "cors"},
				},
			})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	err := adapter.RemovePolicy(context.Background(), server.URL, "Petstore", "rate_limit")
	if err != nil {
		t.Fatalf("expected idempotent success, got error: %v", err)
	}
}

func TestWebMethodsRemovePolicyAPINotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"apiResponse": []map[string]interface{}{}})
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	err := adapter.RemovePolicy(context.Background(), server.URL, "NonExistent", "rate_limit")
	if err == nil {
		t.Fatal("expected error for non-existent API")
	}
	if !strings.Contains(err.Error(), "not found") {
		t.Errorf("expected 'not found' error, got: %v", err)
	}
}

func TestMapPolicyConfig(t *testing.T) {
	result := mapPolicyConfig("throttlingPolicy", map[string]interface{}{
		"maxRequests": 500, "intervalSeconds": 120,
	})
	if result["maxRequestCount"] != 500 {
		t.Errorf("expected maxRequestCount=500, got %v", result["maxRequestCount"])
	}
	if result["intervalInSeconds"] != 120 {
		t.Errorf("expected intervalInSeconds=120, got %v", result["intervalInSeconds"])
	}

	result = mapPolicyConfig("corsPolicy", map[string]interface{}{})
	if result["maxAge"] != 3600 {
		t.Errorf("expected maxAge default 3600, got %v", result["maxAge"])
	}

	input := map[string]interface{}{"custom": "value"}
	result = mapPolicyConfig("unknownType", input)
	if result["custom"] != "value" {
		t.Errorf("expected passthrough for unknown type")
	}
}
