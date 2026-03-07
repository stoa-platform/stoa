package worker

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stoa-platform/stoa/hegemon/daemon/internal/config"
)

func TestTokenCacheFresh(t *testing.T) {
	tc := &TokenCache{
		token:     "cached-token",
		expiresAt: time.Now().Add(5 * time.Minute),
	}
	got, err := tc.Token(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if got != "cached-token" {
		t.Errorf("token = %q, want cached-token", got)
	}
}

func TestTokenCacheExpired(t *testing.T) {
	// Mock KC token endpoint.
	kcServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("method = %s, want POST", r.Method)
		}
		if ct := r.Header.Get("Content-Type"); ct != "application/x-www-form-urlencoded" {
			t.Errorf("content-type = %q, want application/x-www-form-urlencoded", ct)
		}
		json.NewEncoder(w).Encode(tokenResponse{
			AccessToken: "fresh-token",
			ExpiresIn:   300,
			TokenType:   "Bearer",
		})
	}))
	defer kcServer.Close()

	tc := NewTokenCache(kcServer.URL+"/realms/stoa/..", "test-client", "test-secret")
	// Override the keycloakURL and realm to match our test server.
	tc.keycloakURL = kcServer.URL
	tc.realm = "stoa"

	got, err := tc.Token(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if got != "fresh-token" {
		t.Errorf("token = %q, want fresh-token", got)
	}

	// Second call should return cached value.
	got2, err := tc.Token(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if got2 != "fresh-token" {
		t.Errorf("cached token = %q, want fresh-token", got2)
	}
}

func TestTokenCacheRefreshOnExpiry(t *testing.T) {
	var callCount atomic.Int32
	kcServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount.Add(1)
		json.NewEncoder(w).Encode(tokenResponse{
			AccessToken: "new-token",
			ExpiresIn:   300,
		})
	}))
	defer kcServer.Close()

	tc := NewTokenCache(kcServer.URL, "client", "secret")
	// Set an expired token.
	tc.token = "old-token"
	tc.expiresAt = time.Now().Add(-1 * time.Minute)

	got, err := tc.Token(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if got != "new-token" {
		t.Errorf("token = %q, want new-token", got)
	}
	if callCount.Load() != 1 {
		t.Errorf("KC called %d times, want 1", callCount.Load())
	}
}

func TestGatewayExecutorDispatch(t *testing.T) {
	pollCount := 0
	gwServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/hegemon/dispatch" && r.Method == http.MethodPost {
			var req dispatchRequest
			json.NewDecoder(r.Body).Decode(&req)
			if req.TicketID != "CAB-1234" {
				t.Errorf("ticket_id = %q, want CAB-1234", req.TicketID)
			}
			json.NewEncoder(w).Encode(dispatchResponse{
				DispatchID: "d-001",
				Status:     "accepted",
			})
			return
		}
		if r.URL.Path == "/hegemon/dispatch/d-001" && r.Method == http.MethodGet {
			pollCount++
			if pollCount < 2 {
				json.NewEncoder(w).Encode(dispatchStatusResponse{
					DispatchID: "d-001",
					Status:     "running",
				})
				return
			}
			json.NewEncoder(w).Encode(dispatchStatusResponse{
				DispatchID: "d-001",
				Status:     "completed",
				Result: &Result{
					Status:   "done",
					PRNumber: 99,
					Summary:  "all done",
				},
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer gwServer.Close()

	cfg := config.GatewayConfig{
		URL:          gwServer.URL,
		ClientID:     "test",
		ClientSecret: "test",
		KeycloakURL:  "http://unused",
	}
	exec := NewGatewayExecutor(cfg)
	exec.pollInterval = 100 * time.Millisecond // fast polling for tests
	// Pre-fill token cache to skip KC auth.
	exec.tokenCache.token = "test-token"
	exec.tokenCache.expiresAt = time.Now().Add(5 * time.Minute)

	w := &config.WorkerConfig{Name: "worker-1"}
	ctx := context.Background()
	result, _, err := exec.Execute(ctx, w, "CAB-1234", "Test", "desc", 5, 2*time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	if result.Status != "done" {
		t.Errorf("status = %q, want done", result.Status)
	}
	if result.PRNumber != 99 {
		t.Errorf("pr_number = %d, want 99", result.PRNumber)
	}
}

func TestGatewayExecutorRejected(t *testing.T) {
	gwServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(dispatchResponse{
			DispatchID: "",
			Status:     "rejected",
			Reason:     "worker busy",
		})
	}))
	defer gwServer.Close()

	cfg := config.GatewayConfig{URL: gwServer.URL}
	exec := NewGatewayExecutor(cfg)
	exec.tokenCache.token = "test-token"
	exec.tokenCache.expiresAt = time.Now().Add(5 * time.Minute)

	w := &config.WorkerConfig{Name: "worker-1"}
	result, _, err := exec.Execute(context.Background(), w, "CAB-1", "T", "D", 5, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	if result.Status != "failed" {
		t.Errorf("status = %q, want failed", result.Status)
	}
}

func TestHybridFallback(t *testing.T) {
	// Gateway returns 500 → should trigger hybrid fallback in main.go logic.
	// This test verifies the gateway executor returns an error on 500.
	gwServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("internal error"))
	}))
	defer gwServer.Close()

	cfg := config.GatewayConfig{URL: gwServer.URL}
	exec := NewGatewayExecutor(cfg)
	exec.tokenCache.token = "test-token"
	exec.tokenCache.expiresAt = time.Now().Add(5 * time.Minute)

	w := &config.WorkerConfig{Name: "worker-1"}
	_, _, err := exec.Execute(context.Background(), w, "CAB-1", "T", "D", 5, time.Minute)
	if err == nil {
		t.Error("expected error on 500 response")
	}
}

func TestTokenCacheError(t *testing.T) {
	tc := NewTokenCache("http://invalid-host-that-does-not-exist:9999", "c", "s")
	_, err := tc.Token(context.Background())
	if err == nil {
		t.Error("expected error for unreachable KC")
	}
}
