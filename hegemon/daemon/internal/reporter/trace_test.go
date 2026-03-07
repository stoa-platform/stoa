package reporter

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stoa-platform/stoa/hegemon/daemon/internal/worker"
)

func TestTraceReporterSuccess(t *testing.T) {
	var received traceIngestRequest
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-STOA-API-KEY") != "test-key" {
			t.Errorf("expected X-STOA-API-KEY=test-key, got %q", r.Header.Get("X-STOA-API-KEY"))
		}
		if r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("expected Content-Type=application/json, got %q", r.Header.Get("Content-Type"))
		}
		body, _ := io.ReadAll(r.Body)
		if err := json.Unmarshal(body, &received); err != nil {
			t.Fatalf("unmarshal: %v", err)
		}
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"ingested": true, "trace_id": "t-1"}`))
	}))
	defer srv.Close()

	tr := NewTraceReporter(srv.URL, "test-key")
	result := &worker.Result{
		Status:       "done",
		PRNumber:     42,
		Branch:       "feat/cab-1234-test",
		FilesChanged: 5,
		Summary:      "implemented feature",
		CostUSD:      2.50,
	}

	// Call synchronously for testing.
	err := tr.report(t.Context(), "backend", "CAB-1234", result, 22*time.Minute)
	if err != nil {
		t.Fatalf("report: %v", err)
	}

	if received.TriggerType != "ai-session" {
		t.Errorf("trigger_type = %q, want ai-session", received.TriggerType)
	}
	if received.TriggerSource != "hegemon-backend" {
		t.Errorf("trigger_source = %q, want hegemon-backend", received.TriggerSource)
	}
	if received.TenantID != "hegemon" {
		t.Errorf("tenant_id = %q, want hegemon", received.TenantID)
	}
	if received.APIName != "CAB-1234" {
		t.Errorf("api_name = %q, want CAB-1234", received.APIName)
	}
	if received.Status != "success" {
		t.Errorf("status = %q, want success", received.Status)
	}
	if received.TotalDurationMs != 1320000 {
		t.Errorf("total_duration_ms = %d, want 1320000", received.TotalDurationMs)
	}
	// 3 steps: dispatched, pr-created, done
	if len(received.Steps) != 3 {
		t.Errorf("steps count = %d, want 3", len(received.Steps))
	}
	if received.Metadata["cost_usd"] != 2.50 {
		t.Errorf("metadata.cost_usd = %v, want 2.50", received.Metadata["cost_usd"])
	}
	if received.Metadata["pr_number"] != float64(42) {
		t.Errorf("metadata.pr_number = %v, want 42", received.Metadata["pr_number"])
	}
}

func TestTraceReporterFailed(t *testing.T) {
	var received traceIngestRequest
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		json.Unmarshal(body, &received)
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"ingested": true, "trace_id": "t-2"}`))
	}))
	defer srv.Close()

	tr := NewTraceReporter(srv.URL, "test-key")
	result := &worker.Result{
		Status:  "failed",
		Summary: "CI failed",
		CostUSD: 1.00,
	}

	err := tr.report(t.Context(), "mcp", "CAB-5678", result, 5*time.Minute)
	if err != nil {
		t.Fatalf("report: %v", err)
	}

	if received.Status != "failed" {
		t.Errorf("status = %q, want failed", received.Status)
	}
	if received.TriggerSource != "hegemon-mcp" {
		t.Errorf("trigger_source = %q, want hegemon-mcp", received.TriggerSource)
	}
	// 2 steps: dispatched, failed (no pr-created)
	if len(received.Steps) != 2 {
		t.Errorf("steps count = %d, want 2", len(received.Steps))
	}
}

func TestTraceReporterServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(`{"detail": "db error"}`))
	}))
	defer srv.Close()

	tr := NewTraceReporter(srv.URL, "test-key")
	result := &worker.Result{Status: "done", CostUSD: 0.50}

	err := tr.report(t.Context(), "qa", "CAB-9999", result, time.Minute)
	if err == nil {
		t.Fatal("expected error for 500 response")
	}
}

func TestNewTraceReporterNilWhenNotConfigured(t *testing.T) {
	if tr := NewTraceReporter("", "key"); tr != nil {
		t.Error("expected nil when apiURL is empty")
	}
	if tr := NewTraceReporter("http://localhost", ""); tr != nil {
		t.Error("expected nil when ingestKey is empty")
	}
}
