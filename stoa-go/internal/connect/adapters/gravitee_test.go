package adapters

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGraviteeDetect(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/management/v2/organizations/DEFAULT" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]string{"id": "DEFAULT", "name": "Default"})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	adapter := NewGraviteeAdapter(AdapterConfig{Username: "admin", Password: "admin"})
	ok, err := adapter.Detect(context.Background(), server.URL)
	if err != nil {
		t.Fatalf("detect error: %v", err)
	}
	if !ok {
		t.Error("expected Gravitee to be detected")
	}
}

func TestGraviteeDetectNotGravitee(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	adapter := NewGraviteeAdapter(AdapterConfig{})
	ok, err := adapter.Detect(context.Background(), server.URL)
	if err != nil {
		t.Fatalf("detect error: %v", err)
	}
	if ok {
		t.Error("expected Gravitee NOT to be detected")
	}
}

func TestGraviteeDiscover(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/management/v2/environments/DEFAULT/apis":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"data": []map[string]interface{}{
					{
						"id":                "api-1",
						"name":              "Echo API",
						"apiVersion":        "1.0",
						"state":             "STARTED",
						"definitionVersion": "V4",
					},
					{
						"id":                "api-2",
						"name":              "Stopped API",
						"apiVersion":        "2.0",
						"state":             "STOPPED",
						"definitionVersion": "V4",
					},
				},
			})
		case "/management/v2/environments/DEFAULT/apis/api-1":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"listeners": []map[string]interface{}{
					{
						"type":  "HTTP",
						"paths": []map[string]interface{}{{"path": "/echo"}},
					},
				},
				"endpointGroups": []map[string]interface{}{
					{
						"endpoints": []map[string]interface{}{
							{"target": "http://echo-backend:8888"},
						},
					},
				},
			})
		case "/management/v2/environments/DEFAULT/apis/api-2":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{})
		case "/management/v2/environments/DEFAULT/apis/api-1/plans":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"data": []map[string]interface{}{
					{
						"name":   "Rate Plan",
						"status": "PUBLISHED",
						"flows": []map[string]interface{}{
							{"pre": []map[string]interface{}{{"policy": "rate-limit"}}},
						},
					},
				},
			})
		case "/management/v2/environments/DEFAULT/apis/api-2/plans":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"data": []interface{}{}})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewGraviteeAdapter(AdapterConfig{Username: "admin", Password: "admin"})
	apis, err := adapter.Discover(context.Background(), server.URL)
	if err != nil {
		t.Fatalf("discover error: %v", err)
	}
	if len(apis) != 2 {
		t.Fatalf("expected 2 APIs, got %d", len(apis))
	}

	if apis[0].Name != "Echo API" {
		t.Errorf("expected 'Echo API', got %s", apis[0].Name)
	}
	if !apis[0].IsActive {
		t.Error("expected Echo API to be active")
	}
	if apis[0].BackendURL != "http://echo-backend:8888" {
		t.Errorf("unexpected backend URL: %s", apis[0].BackendURL)
	}
	if len(apis[0].Paths) != 1 || apis[0].Paths[0] != "/echo" {
		t.Errorf("unexpected paths: %v", apis[0].Paths)
	}
	if len(apis[0].Policies) != 1 || apis[0].Policies[0] != "rate-limit" {
		t.Errorf("unexpected policies: %v", apis[0].Policies)
	}

	if apis[1].Name != "Stopped API" {
		t.Errorf("expected 'Stopped API', got %s", apis[1].Name)
	}
	if apis[1].IsActive {
		t.Error("expected Stopped API to be inactive")
	}
}

func TestGraviteeDiscoverWithBasicAuth(t *testing.T) {
	var receivedUser, receivedPass string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedUser, receivedPass, _ = r.BasicAuth()
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"data": []interface{}{}})
	}))
	defer server.Close()

	adapter := NewGraviteeAdapter(AdapterConfig{Username: "admin", Password: "secret"})
	_, _ = adapter.Discover(context.Background(), server.URL)

	if receivedUser != "admin" || receivedPass != "secret" {
		t.Errorf("expected basic auth admin:secret, got %s:%s", receivedUser, receivedPass)
	}
}
