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

func TestWebMethodsSyncRoutes(t *testing.T) {
	var createdAPIs []string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
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
	_, err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
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
	_, err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
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
	_, err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
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
	if _, err := adapter.SyncRoutes(context.Background(), server.URL, routes); err != nil {
		t.Fatalf("first sync error: %v", err)
	}
	if syncCount != 1 {
		t.Fatalf("expected 1 sync on first call, got %d", syncCount)
	}

	// Second sync with same hash: should skip
	syncCount = 0
	if _, err := adapter.SyncRoutes(context.Background(), server.URL, routes); err != nil {
		t.Fatalf("second sync error: %v", err)
	}
	if syncCount != 0 {
		t.Errorf("expected 0 syncs (hash unchanged), got %d", syncCount)
	}

	// Third sync with different hash: should sync again
	routes[0].SpecHash = "def456"
	syncCount = 0
	if _, err := adapter.SyncRoutes(context.Background(), server.URL, routes); err != nil {
		t.Fatalf("third sync error: %v", err)
	}
	if syncCount != 1 {
		t.Errorf("expected 1 sync (hash changed), got %d", syncCount)
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
	_, err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
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
