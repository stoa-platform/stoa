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
	_, err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
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
	_, err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
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
	_, err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "petstore", BackendURL: "http://example.com", PathPrefix: "/pets", Methods: []string{"GET"}, Activated: true},
	})
	if err == nil {
		t.Fatal("expected error when activation fails, got nil")
	}
	if !strings.Contains(err.Error(), "stoa-petstore") {
		t.Errorf("error should contain API name, got: %s", err.Error())
	}
}

// TestRegressionFailedRoutesTracking — CAB-1944: SyncResult.FailedRoutes
// should track per-deployment errors. After GO-1 fix (C.3/C.6), the per-route
// failure map is a return value, not a shared field — concurrent SyncRoutes
// calls no longer clobber each other.
func TestRegressionFailedRoutesTracking(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"apiResponse":[]}`))
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodPost:
			body, _ := io.ReadAll(r.Body)
			var payload map[string]interface{}
			_ = json.Unmarshal(body, &payload)
			name := payload["apiName"].(string)
			if name == "stoa-bad-route" {
				w.WriteHeader(http.StatusInternalServerError)
				_, _ = w.Write([]byte(`{"errorDetails":"RefProperty crash"}`))
				return
			}
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusCreated)
			_, _ = w.Write([]byte(`{"apiResponse":{"api":{"id":"ok-1","isActive":true}}}`))
		case strings.Contains(r.URL.Path, "/rest/apigateway/apis/") && r.Method == http.MethodGet:
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"apiResponse":{"api":{"id":"ok-1","isActive":true}}}`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	result, err := adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "good-route", DeploymentID: "dep-1", Activated: true},
		{Name: "bad-route", DeploymentID: "dep-2", Activated: true},
	})

	if err == nil {
		t.Fatal("expected error")
	}

	// dep-1 should NOT be in FailedRoutes (it succeeded)
	if _, failed := result.FailedRoutes["dep-1"]; failed {
		t.Error("dep-1 should not be in FailedRoutes (it succeeded)")
	}
	// dep-2 should be in FailedRoutes
	if errMsg, failed := result.FailedRoutes["dep-2"]; !failed {
		t.Error("dep-2 should be in FailedRoutes")
	} else if !strings.Contains(errMsg, "RefProperty") {
		t.Errorf("dep-2 error should contain RefProperty, got: %s", errMsg)
	}
}
