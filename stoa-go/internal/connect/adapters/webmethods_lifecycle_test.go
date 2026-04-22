package adapters

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

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
