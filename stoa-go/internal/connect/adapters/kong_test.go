package adapters

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestKongDetect(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]string{
				"tagline": "Welcome to kong",
				"version": "3.6.0",
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	adapter := NewKongAdapter(AdapterConfig{})
	ok, err := adapter.Detect(context.Background(), server.URL)
	if err != nil {
		t.Fatalf("detect error: %v", err)
	}
	if !ok {
		t.Error("expected Kong to be detected")
	}
}

func TestKongDetectNotKong(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	}))
	defer server.Close()

	adapter := NewKongAdapter(AdapterConfig{})
	ok, err := adapter.Detect(context.Background(), server.URL)
	if err != nil {
		t.Fatalf("detect error: %v", err)
	}
	if ok {
		t.Error("expected Kong NOT to be detected")
	}
}

// TestKongDetectUnreachable — GO-1 M.3 behaviour flip: Detect now propagates
// network errors (pre-M.3 it silently returned `(false, nil)` on unreachable
// hosts, which was indistinguishable from "host up but not Kong"). The
// autoDetect caller in connect/discovery.go already handles the error by
// logging and trying the next gateway, so the contract for auto-detection
// is unchanged — only the observability improved.
func TestKongDetectUnreachable(t *testing.T) {
	adapter := NewKongAdapter(AdapterConfig{})
	ok, err := adapter.Detect(context.Background(), "http://127.0.0.1:1")
	if err == nil {
		t.Fatal("expected network error to be propagated after GO-1 M.3")
	}
	if ok {
		t.Error("expected false for unreachable host")
	}
}

func TestKongDiscover(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/services":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"data": []map[string]interface{}{
					{
						"id":       "svc-1",
						"name":     "echo-service",
						"host":     "echo-backend",
						"port":     8888,
						"protocol": "http",
						"path":     "/",
						"enabled":  true,
					},
					{
						"id":       "svc-2",
						"name":     "api-service",
						"host":     "api-backend",
						"port":     3000,
						"protocol": "https",
						"path":     "/api",
						"enabled":  false,
					},
				},
			})
		case "/services/svc-1/routes":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"data": []map[string]interface{}{
					{"id": "rt-1", "paths": []string{"/echo"}, "methods": []string{"GET", "POST"}},
				},
			})
		case "/services/svc-2/routes":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"data": []map[string]interface{}{
					{"id": "rt-2", "paths": []string{"/api/v1"}, "methods": []string{"GET"}},
				},
			})
		case "/services/svc-1/plugins":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"data": []map[string]interface{}{
					{"name": "rate-limiting"},
				},
			})
		case "/services/svc-2/plugins":
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"data": []map[string]interface{}{},
			})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewKongAdapter(AdapterConfig{})
	apis, err := adapter.Discover(context.Background(), server.URL)
	if err != nil {
		t.Fatalf("discover error: %v", err)
	}
	if len(apis) != 2 {
		t.Fatalf("expected 2 APIs, got %d", len(apis))
	}

	// Check first API
	if apis[0].Name != "echo-service" {
		t.Errorf("expected echo-service, got %s", apis[0].Name)
	}
	if !apis[0].IsActive {
		t.Error("expected echo-service to be active")
	}
	if apis[0].BackendURL != "http://echo-backend:8888/" {
		t.Errorf("unexpected backend URL: %s", apis[0].BackendURL)
	}
	if len(apis[0].Paths) != 1 || apis[0].Paths[0] != "/echo" {
		t.Errorf("unexpected paths: %v", apis[0].Paths)
	}
	if len(apis[0].Policies) != 1 || apis[0].Policies[0] != "rate-limiting" {
		t.Errorf("unexpected policies: %v", apis[0].Policies)
	}

	// Check second API
	if apis[1].Name != "api-service" {
		t.Errorf("expected api-service, got %s", apis[1].Name)
	}
	if apis[1].IsActive {
		t.Error("expected api-service to be inactive")
	}
}

func TestKongDiscoverWithToken(t *testing.T) {
	var receivedToken string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedToken = r.Header.Get("Kong-Admin-Token")
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"data": []interface{}{}})
	}))
	defer server.Close()

	adapter := NewKongAdapter(AdapterConfig{Token: "my-secret-token"})
	_, _ = adapter.Discover(context.Background(), server.URL)

	if receivedToken != "my-secret-token" {
		t.Errorf("expected Kong-Admin-Token header, got %q", receivedToken)
	}
}

func TestKongDiscoverEmptyServices(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"data": []interface{}{}})
	}))
	defer server.Close()

	adapter := NewKongAdapter(AdapterConfig{})
	apis, err := adapter.Discover(context.Background(), server.URL)
	if err != nil {
		t.Fatalf("discover error: %v", err)
	}
	if len(apis) != 0 {
		t.Errorf("expected 0 APIs, got %d", len(apis))
	}
}
