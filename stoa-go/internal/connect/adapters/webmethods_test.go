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

func TestWebMethodsSyncRoutes(t *testing.T) {
	var createdAPIs []string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			// No existing APIs
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"apiResponse": []interface{}{}})
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodPost:
			body, _ := io.ReadAll(r.Body)
			var payload map[string]interface{}
			_ = json.Unmarshal(body, &payload)
			createdAPIs = append(createdAPIs, payload["apiName"].(string))
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "new-api-1"})
		case r.URL.Path == "/rest/apigateway/apis/new-api-1" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "new-api-1", "apiName": "stoa-petstore", "isActive": true})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "admin"})
	err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "petstore", BackendURL: "http://petstore.example.com", PathPrefix: "/pets", Methods: []string{"GET"}, Activated: true},
	})
	if err != nil {
		t.Fatalf("sync routes error: %v", err)
	}
	if len(createdAPIs) != 1 || createdAPIs[0] != "stoa-petstore" {
		t.Errorf("expected [stoa-petstore], got %v", createdAPIs)
	}
}

func TestWebMethodsSyncRoutesIdempotent(t *testing.T) {
	var putCount, postCount int

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			// API already exists
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "existing-1", "apiName": "stoa-petstore", "apiVersion": "1.0", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/existing-1" && r.Method == http.MethodPut:
			putCount++
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "existing-1"})
		case r.URL.Path == "/rest/apigateway/apis/existing-1" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "existing-1", "apiName": "stoa-petstore", "isActive": true})
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodPost:
			postCount++
			w.WriteHeader(http.StatusCreated)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "admin"})
	err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "petstore", BackendURL: "http://petstore.example.com", PathPrefix: "/pets", Methods: []string{"GET"}, Activated: true},
	})
	if err != nil {
		t.Fatalf("sync routes error: %v", err)
	}
	if putCount != 1 {
		t.Errorf("expected 1 PUT (update), got %d", putCount)
	}
	if postCount != 0 {
		t.Errorf("expected 0 POST (no duplicate create), got %d", postCount)
	}
}

func TestWebMethodsSyncRoutesSkipInactive(t *testing.T) {
	var createCount int

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"apiResponse": []interface{}{}})
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodPost:
			createCount++
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "new-active-1"})
		case strings.HasPrefix(r.URL.Path, "/rest/apigateway/apis/") && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "new-active-1", "apiName": "stoa-active-route", "isActive": true})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "active-route", BackendURL: "http://example.com", PathPrefix: "/a", Methods: []string{"GET"}, Activated: true},
		{Name: "inactive-route", BackendURL: "http://example.com", PathPrefix: "/b", Methods: []string{"GET"}, Activated: false},
	})
	if err != nil {
		t.Fatalf("sync routes error: %v", err)
	}
	// Only 1 POST for the active route, inactive is skipped before any HTTP call
	if createCount != 1 {
		t.Errorf("expected 1 create request (inactive skipped), got %d", createCount)
	}
}

func TestWebMethodsSyncRoutesSpecHashSkip(t *testing.T) {
	var syncCount int

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"apiResponse": []interface{}{}})
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodPost:
			syncCount++
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "new-1"})
		case strings.HasPrefix(r.URL.Path, "/rest/apigateway/apis/") && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "new-1", "apiName": "stoa-petstore", "isActive": true})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	routes := []Route{
		{Name: "petstore", BackendURL: "http://example.com", PathPrefix: "/pets", Methods: []string{"GET"}, Activated: true, SpecHash: "abc123"},
	}

	// First sync: should create
	if err := adapter.SyncRoutes(context.Background(), server.URL, routes); err != nil {
		t.Fatalf("first sync error: %v", err)
	}
	if syncCount != 1 {
		t.Fatalf("expected 1 sync on first call, got %d", syncCount)
	}

	// Second sync with same hash: should skip
	syncCount = 0
	if err := adapter.SyncRoutes(context.Background(), server.URL, routes); err != nil {
		t.Fatalf("second sync error: %v", err)
	}
	if syncCount != 0 {
		t.Errorf("expected 0 syncs (hash unchanged), got %d", syncCount)
	}

	// Third sync with different hash: should sync again
	routes[0].SpecHash = "def456"
	syncCount = 0
	if err := adapter.SyncRoutes(context.Background(), server.URL, routes); err != nil {
		t.Fatalf("third sync error: %v", err)
	}
	if syncCount != 1 {
		t.Errorf("expected 1 sync (hash changed), got %d", syncCount)
	}
}

func TestWebMethodsInjectCredentialsWithAPIAssociation(t *testing.T) {
	var appCreated bool
	var associatedPath string
	var associatedPayload map[string]interface{}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/applications" && r.Method == http.MethodPost:
			appCreated = true
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "app-42"})
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "api-99", "apiName": "Petstore", "apiVersion": "1.0", "isActive": true},
				},
			})
		case strings.HasPrefix(r.URL.Path, "/rest/apigateway/applications/") && strings.HasSuffix(r.URL.Path, "/apis") && r.Method == http.MethodPost:
			associatedPath = r.URL.Path
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &associatedPayload)
			w.WriteHeader(http.StatusOK)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "admin"})
	err := adapter.InjectCredentials(context.Background(), server.URL, []Credential{
		{ConsumerID: "user-1", APIName: "Petstore", Key: "key-abc", AuthType: "key-auth"},
	})
	if err != nil {
		t.Fatalf("inject credentials error: %v", err)
	}
	if !appCreated {
		t.Error("expected application to be created")
	}
	if associatedPath != "/rest/apigateway/applications/app-42/apis" {
		t.Errorf("expected association to app-42, got path: %s", associatedPath)
	}
	apiIDs, ok := associatedPayload["apiIDs"].([]interface{})
	if !ok || len(apiIDs) != 1 || apiIDs[0] != "api-99" {
		t.Errorf("expected apiIDs=[api-99], got %v", associatedPayload["apiIDs"])
	}
}

func TestWebMethodsResolveAPIIDSingleFetch(t *testing.T) {
	var fetchCount int

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet {
			fetchCount++
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "api-single", "apiName": "Petstore", "apiVersion": "1.0", "isActive": true},
				},
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	id, err := adapter.resolveAPIID(context.Background(), server.URL, "Petstore")
	if err != nil {
		t.Fatalf("resolve error: %v", err)
	}
	if id != "api-single" {
		t.Errorf("expected api-single, got %s", id)
	}
	if fetchCount != 1 {
		t.Errorf("expected exactly 1 HTTP call to /apis, got %d", fetchCount)
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

// --- OIDC + Alias Tests ---

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

// --- Telemetry + Config Tests ---

func TestWebMethodsTelemetrySubscribe(t *testing.T) {
	var receivedPayload map[string]interface{}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path == "/rest/apigateway/subscriptions" && r.Method == http.MethodPost {
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &receivedPayload)
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "sub-123"})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	subID, err := adapter.SubscribeTelemetry(context.Background(), server.URL, "http://stoa-connect:8090/webhook/events")
	if err != nil {
		t.Fatalf("subscribe telemetry error: %v", err)
	}
	if subID != "sub-123" {
		t.Errorf("expected subscription ID sub-123, got %s", subID)
	}
	if receivedPayload["eventType"] != "transactionalEvents" {
		t.Errorf("expected eventType=transactionalEvents, got %v", receivedPayload["eventType"])
	}
	if receivedPayload["callbackURL"] != "http://stoa-connect:8090/webhook/events" {
		t.Errorf("unexpected callbackURL: %v", receivedPayload["callbackURL"])
	}
}

func TestWebMethodsTelemetryPoll(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if strings.HasPrefix(r.URL.Path, "/rest/apigateway/transactionalEvents") {
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"transactionalEvents": []map[string]interface{}{
					{
						"eventTimestamp": "1711500000000",
						"apiId":          "api-1",
						"apiName":        "Petstore",
						"httpMethod":     "GET",
						"resourcePath":   "/pets",
						"status":         200,
						"totalTime":      42,
						"tenantId":       "tenant-acme",
					},
					{
						"eventTimestamp": "1711500001000",
						"apiId":          "api-2",
						"apiName":        "Orders",
						"httpMethod":     "POST",
						"resourcePath":   "/orders",
						"status":         201,
						"totalTime":      150,
					},
				},
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	events, err := adapter.PollTelemetry(context.Background(), server.URL, 1711500000000, 1711500002000)
	if err != nil {
		t.Fatalf("poll telemetry error: %v", err)
	}
	if len(events) != 2 {
		t.Fatalf("expected 2 events, got %d", len(events))
	}
	if events[0].Method != "GET" || events[0].Path != "/pets" || events[0].Status != 200 {
		t.Errorf("event 0 mismatch: %+v", events[0])
	}
	if events[0].TenantID != "tenant-acme" {
		t.Errorf("expected tenant-acme, got %s", events[0].TenantID)
	}
	if events[1].LatencyMs != 150 {
		t.Errorf("expected latency 150ms, got %d", events[1].LatencyMs)
	}
}

func TestWebMethodsApplyConfigTelemetry(t *testing.T) {
	var receivedPath string
	var receivedPayload map[string]interface{}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if strings.HasPrefix(r.URL.Path, "/rest/apigateway/configurations/") && r.Method == http.MethodPut {
			receivedPath = r.URL.Path
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &receivedPayload)
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	err := adapter.ApplyConfig(context.Background(), server.URL, "errorProcessing", map[string]interface{}{
		"errorDestination": "designTimeErrorDestination",
		"logLevel":         "ERROR",
	})
	if err != nil {
		t.Fatalf("apply config error: %v", err)
	}
	if receivedPath != "/rest/apigateway/configurations/errorProcessing" {
		t.Errorf("unexpected path: %s", receivedPath)
	}
	if receivedPayload["logLevel"] != "ERROR" {
		t.Errorf("expected logLevel=ERROR, got %v", receivedPayload["logLevel"])
	}
}

func TestWebMethodsEventNormalization(t *testing.T) {
	raw := wmTransactionalEvent{
		EventTimestamp: "1711500000000",
		APIID:          "api-42",
		APIName:        "Petstore",
		HTTPMethod:     "DELETE",
		ResourcePath:   "/pets/123",
		Status:         204,
		TotalTime:      7,
		TenantID:       "tenant-xyz",
	}

	event := NormalizeEvent(raw)
	if event.Method != "DELETE" {
		t.Errorf("expected DELETE, got %s", event.Method)
	}
	if event.Path != "/pets/123" {
		t.Errorf("expected /pets/123, got %s", event.Path)
	}
	if event.Status != 204 {
		t.Errorf("expected 204, got %d", event.Status)
	}
	if event.LatencyMs != 7 {
		t.Errorf("expected 7ms, got %d", event.LatencyMs)
	}
	if event.TenantID != "tenant-xyz" {
		t.Errorf("expected tenant-xyz, got %s", event.TenantID)
	}
	if event.APIID != "api-42" {
		t.Errorf("expected api-42, got %s", event.APIID)
	}
	if event.Timestamp.UnixMilli() != 1711500000000 {
		t.Errorf("unexpected timestamp: %v", event.Timestamp)
	}

	// Test fallback: operationName used when httpMethod is empty
	rawNoMethod := wmTransactionalEvent{
		OperationName: "getPets",
		ResourcePath:  "/pets",
		Status:        200,
	}
	event2 := NormalizeEvent(rawNoMethod)
	if event2.Method != "getPets" {
		t.Errorf("expected operationName fallback, got %s", event2.Method)
	}
}

// --- Robustness Tests (CAB-1927) ---

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

func TestWebMethodsDeleteAPI(t *testing.T) {
	var deactivated, deleted bool

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "api-del-1", "apiName": "Petstore", "apiVersion": "1.0", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/api-del-1/deactivate" && r.Method == http.MethodPut:
			deactivated = true
			w.WriteHeader(http.StatusOK)
		case r.URL.Path == "/rest/apigateway/apis/api-del-1" && r.Method == http.MethodDelete:
			deleted = true
			w.WriteHeader(http.StatusNoContent)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	err := adapter.DeleteAPI(context.Background(), server.URL, "Petstore")
	if err != nil {
		t.Fatalf("delete api error: %v", err)
	}
	if !deactivated {
		t.Error("expected deactivate to be called before delete")
	}
	if !deleted {
		t.Error("expected delete to be called")
	}
}

func TestWebMethodsDeleteAPINotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"apiResponse": []interface{}{}})
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	err := adapter.DeleteAPI(context.Background(), server.URL, "NonExistent")
	if err != nil {
		t.Fatalf("expected idempotent success for non-existent API, got error: %v", err)
	}
}

func TestWebMethodsOpenAPI31Downgrade(t *testing.T) {
	spec31 := []byte(`{"openapi": "3.1.0", "info": {"title": "Test"}}`)
	result := downgradeOpenAPI31(spec31)
	expected := `{"openapi": "3.0.3", "info": {"title": "Test"}}`
	if string(result) != expected {
		t.Errorf("expected %s, got %s", expected, string(result))
	}

	spec311 := []byte(`{"openapi": "3.1.1", "info": {"title": "Test"}}`)
	result311 := downgradeOpenAPI31(spec311)
	if !strings.Contains(string(result311), `"3.0.3"`) {
		t.Errorf("expected 3.0.3, got %s", string(result311))
	}

	spec30 := []byte(`{"openapi": "3.0.2", "info": {"title": "Test"}}`)
	result30 := downgradeOpenAPI31(spec30)
	if string(result30) != string(spec30) {
		t.Errorf("expected 3.0.2 unchanged, got %s", string(result30))
	}
}

func TestWebMethodsActivateDeactivate(t *testing.T) {
	var activateCalled, deactivateCalled bool

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/rest/apigateway/apis/api-lifecycle/activate" && r.Method == http.MethodPut:
			activateCalled = true
			w.WriteHeader(http.StatusOK)
		case r.URL.Path == "/rest/apigateway/apis/api-lifecycle/deactivate" && r.Method == http.MethodPut:
			deactivateCalled = true
			w.WriteHeader(http.StatusOK)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})

	if err := adapter.ActivateAPI(context.Background(), server.URL, "api-lifecycle"); err != nil {
		t.Fatalf("activate error: %v", err)
	}
	if !activateCalled {
		t.Error("expected activate to be called")
	}

	if err := adapter.DeactivateAPI(context.Background(), server.URL, "api-lifecycle"); err != nil {
		t.Fatalf("deactivate error: %v", err)
	}
	if !deactivateCalled {
		t.Error("expected deactivate to be called")
	}
}

func TestWebMethodsSyncRoutesWithDeactivation(t *testing.T) {
	var deactivateCalled bool
	var createCount int

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "existing-deact", "apiName": "stoa-old-route", "apiVersion": "1.0", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/existing-deact/deactivate" && r.Method == http.MethodPut:
			deactivateCalled = true
			w.WriteHeader(http.StatusOK)
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodPost:
			createCount++
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "new-1"})
		case r.URL.Path == "/rest/apigateway/apis/new-1" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "new-1", "apiName": "stoa-new-route", "isActive": true})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "manage"})
	err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "old-route", BackendURL: "http://example.com", PathPrefix: "/old", Methods: []string{"GET"}, Activated: false},
		{Name: "new-route", BackendURL: "http://example.com", PathPrefix: "/new", Methods: []string{"POST"}, Activated: true},
	})
	if err != nil {
		t.Fatalf("sync routes error: %v", err)
	}
	if !deactivateCalled {
		t.Error("expected deactivate to be called for inactive route")
	}
	if createCount != 1 {
		t.Errorf("expected 1 create for active route, got %d", createCount)
	}
}

func TestWebMethodsSyncRoutesVerifiesActiveAfterCreate(t *testing.T) {
	var getVerifyCalled bool

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"apiResponse": []interface{}{}})
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodPost:
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "created-1"})
		case r.URL.Path == "/rest/apigateway/apis/created-1" && r.Method == http.MethodGet:
			getVerifyCalled = true
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"id": "created-1", "apiName": "stoa-petstore", "isActive": true,
			})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "admin"})
	err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "petstore", BackendURL: "http://example.com", PathPrefix: "/pets", Methods: []string{"GET"}, Activated: true},
	})
	if err != nil {
		t.Fatalf("sync routes error: %v", err)
	}
	if !getVerifyCalled {
		t.Error("expected GET verification call after POST create")
	}
}

func TestWebMethodsSyncRoutesActivatesIfNotActive(t *testing.T) {
	var activateCalled bool

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "existing-1", "apiName": "stoa-petstore", "apiVersion": "1.0", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/existing-1" && r.Method == http.MethodPut:
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "existing-1"})
		case r.URL.Path == "/rest/apigateway/apis/existing-1" && r.Method == http.MethodGet:
			// API is NOT active after PUT
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"id": "existing-1", "apiName": "stoa-petstore", "isActive": false,
			})
		case r.URL.Path == "/rest/apigateway/apis/existing-1/activate" && r.Method == http.MethodPut:
			activateCalled = true
			w.WriteHeader(http.StatusOK)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "admin"})
	err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "petstore", BackendURL: "http://example.com", PathPrefix: "/pets", Methods: []string{"GET"}, Activated: true},
	})
	if err != nil {
		t.Fatalf("sync routes error: %v", err)
	}
	if !activateCalled {
		t.Error("expected ActivateAPI to be called when isActive=false")
	}
}

func TestWebMethodsSyncRoutesFailsIfActivateFails(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"apiResponse": []map[string]interface{}{
					{"id": "existing-1", "apiName": "stoa-petstore", "apiVersion": "1.0", "isActive": true},
				},
			})
		case r.URL.Path == "/rest/apigateway/apis/existing-1" && r.Method == http.MethodPut:
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "existing-1"})
		case r.URL.Path == "/rest/apigateway/apis/existing-1" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"id": "existing-1", "apiName": "stoa-petstore", "isActive": false,
			})
		case r.URL.Path == "/rest/apigateway/apis/existing-1/activate" && r.Method == http.MethodPut:
			w.WriteHeader(http.StatusInternalServerError)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{Username: "admin", Password: "admin"})
	err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "petstore", BackendURL: "http://example.com", PathPrefix: "/pets", Methods: []string{"GET"}, Activated: true},
	})
	if err == nil {
		t.Fatal("expected error when activation fails, got nil")
	}
	if !strings.Contains(err.Error(), "stoa-petstore") {
		t.Errorf("error should contain API name, got: %s", err.Error())
	}
}

// --- Regression tests for CAB-1944 ---

func TestRegressionSanitizeWMName(t *testing.T) {
	// CAB-1944: webMethods rejects apiName with em-dash, parentheses, spaces
	cases := []struct {
		input    string
		expected string
	}{
		{"stoa-IA — Chat Completions (GPT-4o)", "stoa-IA---Chat-Completions--GPT-4o-"},
		{"stoa-simple-api", "stoa-simple-api"},
		{"stoa-api with spaces", "stoa-api-with-spaces"},
		{"stoa-api/v2", "stoa-api-v2"},
		{"stoa-api_test.v1", "stoa-api_test.v1"},
	}
	for _, tc := range cases {
		result := sanitizeWMName(tc.input)
		if result != tc.expected {
			t.Errorf("sanitizeWMName(%q) = %q, want %q", tc.input, result, tc.expected)
		}
	}
}

func TestRegressionFixExternalDocsObject(t *testing.T) {
	// CAB-1944: webMethods expects externalDocs as array, Swagger 2.0 has it as object
	specObj := []byte(`{"swagger":"2.0","info":{"title":"Test"},"externalDocs":{"description":"Find more","url":"http://example.com"}}`)
	result := fixExternalDocs(specObj)

	var parsed map[string]interface{}
	if err := json.Unmarshal(result, &parsed); err != nil {
		t.Fatalf("failed to parse result: %v", err)
	}
	ed, ok := parsed["externalDocs"]
	if !ok {
		t.Fatal("externalDocs missing from result")
	}
	arr, isArr := ed.([]interface{})
	if !isArr {
		t.Fatalf("externalDocs should be array, got %T", ed)
	}
	if len(arr) != 1 {
		t.Fatalf("externalDocs array should have 1 element, got %d", len(arr))
	}
}

func TestRegressionFixExternalDocsAlreadyArray(t *testing.T) {
	// No-op when externalDocs is already an array
	specArr := []byte(`{"swagger":"2.0","externalDocs":[{"url":"http://example.com"}]}`)
	result := fixExternalDocs(specArr)
	if string(result) != string(specArr) {
		t.Errorf("expected unchanged spec, got %s", string(result))
	}
}

func TestRegressionFixExternalDocsAbsent(t *testing.T) {
	// No-op when externalDocs is absent
	specNone := []byte(`{"openapi":"3.0.0","info":{"title":"Test"}}`)
	result := fixExternalDocs(specNone)
	if string(result) != string(specNone) {
		t.Errorf("expected unchanged spec, got %s", string(result))
	}
}

func TestRegressionSyncErrorIncludesBody(t *testing.T) {
	// CAB-1944: error message should include response body for debugging
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"apiResponse":[]}`))
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodPost:
			w.WriteHeader(http.StatusBadRequest)
			_, _ = w.Write([]byte(`{"errorDetails":" Invalid field data: apiName"}`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "bad-name", Activated: true},
	})
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !strings.Contains(err.Error(), "Invalid field data") {
		t.Errorf("error should include response body, got: %s", err.Error())
	}
}
