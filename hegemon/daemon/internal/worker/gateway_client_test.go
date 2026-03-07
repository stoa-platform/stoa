package worker

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func newTestGatewayClient(handler http.Handler) (*GatewayClient, *httptest.Server) {
	server := httptest.NewServer(handler)
	tc := &TokenCache{
		token:     "test-token",
		expiresAt: time.Now().Add(5 * time.Minute),
	}
	client := NewGatewayClient(server.URL, tc)
	return client, server
}

// --- Budget Tests (CAB-1717) ---

func TestCheckBudgetAllowed(t *testing.T) {
	gc, server := newTestGatewayClient(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/hegemon/budget/fleet" {
			t.Errorf("path = %q, want /hegemon/budget/fleet", r.URL.Path)
		}
		if r.Method != http.MethodGet {
			t.Errorf("method = %s, want GET", r.Method)
		}
		if auth := r.Header.Get("Authorization"); auth != "Bearer test-token" {
			t.Errorf("auth = %q, want Bearer test-token", auth)
		}
		json.NewEncoder(w).Encode(BudgetStatus{
			Allowed:    true,
			DailyCost:  15.50,
			DailyLimit: 50.00,
		})
	}))
	defer server.Close()

	status, err := gc.CheckBudget(context.Background(), "fleet")
	if err != nil {
		t.Fatal(err)
	}
	if !status.Allowed {
		t.Error("budget should be allowed")
	}
	if status.DailyCost != 15.50 {
		t.Errorf("daily_cost = %f, want 15.50", status.DailyCost)
	}
}

func TestCheckBudgetDenied(t *testing.T) {
	gc, server := newTestGatewayClient(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(BudgetStatus{
			Allowed:    false,
			DailyCost:  52.00,
			DailyLimit: 50.00,
			Reason:     "daily limit exceeded",
		})
	}))
	defer server.Close()

	status, err := gc.CheckBudget(context.Background(), "fleet")
	if err != nil {
		t.Fatal(err)
	}
	if status.Allowed {
		t.Error("budget should be denied")
	}
	if status.Reason != "daily limit exceeded" {
		t.Errorf("reason = %q", status.Reason)
	}
}

func TestCheckBudgetServerError(t *testing.T) {
	gc, server := newTestGatewayClient(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("internal error"))
	}))
	defer server.Close()

	_, err := gc.CheckBudget(context.Background(), "fleet")
	if err == nil {
		t.Error("expected error on 500")
	}
}

func TestRecordCostSuccess(t *testing.T) {
	gc, server := newTestGatewayClient(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/hegemon/budget/worker-1/cost" {
			t.Errorf("path = %q, want /hegemon/budget/worker-1/cost", r.URL.Path)
		}
		if r.Method != http.MethodPost {
			t.Errorf("method = %s, want POST", r.Method)
		}
		var cr costRecord
		json.NewDecoder(r.Body).Decode(&cr)
		if cr.CostUSD != 2.50 {
			t.Errorf("cost_usd = %f, want 2.50", cr.CostUSD)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	err := gc.RecordCost(context.Background(), "worker-1", 2.50)
	if err != nil {
		t.Fatal(err)
	}
}

func TestRecordCostServerError(t *testing.T) {
	gc, server := newTestGatewayClient(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
		w.Write([]byte("unavailable"))
	}))
	defer server.Close()

	err := gc.RecordCost(context.Background(), "worker-1", 1.00)
	if err == nil {
		t.Error("expected error on 503")
	}
}

// --- Claims Tests (CAB-1719) ---

func TestReserveClaimSuccess(t *testing.T) {
	gc, server := newTestGatewayClient(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/hegemon/claims/CAB-1290/reserve" {
			t.Errorf("path = %q", r.URL.Path)
		}
		if r.Method != http.MethodPost {
			t.Errorf("method = %s, want POST", r.Method)
		}
		var cr claimRequest
		json.NewDecoder(r.Body).Decode(&cr)
		if cr.Owner != "worker-1" {
			t.Errorf("owner = %q, want worker-1", cr.Owner)
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	err := gc.ReserveClaim(context.Background(), "CAB-1290", "worker-1")
	if err != nil {
		t.Fatal(err)
	}
}

func TestReserveClaimConflict(t *testing.T) {
	gc, server := newTestGatewayClient(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusConflict)
		w.Write([]byte(`{"error":"already claimed by worker-2"}`))
	}))
	defer server.Close()

	err := gc.ReserveClaim(context.Background(), "CAB-1290", "worker-1")
	if err != ErrClaimConflict {
		t.Errorf("err = %v, want ErrClaimConflict", err)
	}
}

func TestReleaseClaimSuccess(t *testing.T) {
	gc, server := newTestGatewayClient(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/hegemon/claims/CAB-1290/release" {
			t.Errorf("path = %q", r.URL.Path)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	err := gc.ReleaseClaim(context.Background(), "CAB-1290", "worker-1")
	if err != nil {
		t.Fatal(err)
	}
}

func TestHeartbeatSuccess(t *testing.T) {
	gc, server := newTestGatewayClient(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/hegemon/claims/CAB-1290/heartbeat" {
			t.Errorf("path = %q", r.URL.Path)
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	err := gc.Heartbeat(context.Background(), "CAB-1290", "worker-1")
	if err != nil {
		t.Fatal(err)
	}
}

func TestHeartbeatServerError(t *testing.T) {
	gc, server := newTestGatewayClient(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		w.Write([]byte("bad gateway"))
	}))
	defer server.Close()

	err := gc.Heartbeat(context.Background(), "CAB-1290", "worker-1")
	if err == nil {
		t.Error("expected error on 502")
	}
}

func TestReserveClaimServerError(t *testing.T) {
	gc, server := newTestGatewayClient(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("internal error"))
	}))
	defer server.Close()

	err := gc.ReserveClaim(context.Background(), "CAB-1290", "worker-1")
	if err == nil {
		t.Error("expected error on 500")
	}
	if err == ErrClaimConflict {
		t.Error("should not be ErrClaimConflict on 500")
	}
}
