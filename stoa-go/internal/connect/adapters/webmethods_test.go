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
	var requestCount int

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet {
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"apiResponse": []interface{}{}})
			return
		}
		requestCount++
		w.WriteHeader(http.StatusOK)
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
	if requestCount != 1 {
		t.Errorf("expected 1 create request (inactive skipped), got %d", requestCount)
	}
}

func TestWebMethodsSyncRoutesSpecHashSkip(t *testing.T) {
	var syncCount int

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet {
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"apiResponse": []interface{}{}})
			return
		}
		syncCount++
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "new-1"})
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
