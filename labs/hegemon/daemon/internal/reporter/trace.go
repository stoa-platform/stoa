package reporter

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"

	"github.com/stoa-platform/stoa/hegemon/daemon/internal/worker"
)

// TraceReporter pushes session summaries to the STOA Control Plane API.
// Endpoint: POST /v1/traces/ingest (X-STOA-API-KEY auth).
type TraceReporter struct {
	apiURL    string
	ingestKey string
	http      *http.Client
}

// NewTraceReporter creates a trace reporter. Returns nil if not configured.
func NewTraceReporter(apiURL, ingestKey string) *TraceReporter {
	if apiURL == "" || ingestKey == "" {
		return nil
	}
	return &TraceReporter{
		apiURL:    apiURL,
		ingestKey: ingestKey,
		http:      &http.Client{Timeout: 10 * time.Second},
	}
}

// traceStep is a step in an AI session trace.
type traceStep struct {
	Name      string `json:"name"`
	Status    string `json:"status"`
	DurationMs int   `json:"duration_ms,omitempty"`
	Error     string `json:"error,omitempty"`
}

// traceIngestRequest matches AISessionIngestRequest in control-plane-api.
type traceIngestRequest struct {
	TriggerType    string            `json:"trigger_type"`
	TriggerSource  string            `json:"trigger_source"`
	TenantID       string            `json:"tenant_id"`
	APIName        string            `json:"api_name"`
	Environment    string            `json:"environment"`
	GitBranch      string            `json:"git_branch,omitempty"`
	GitAuthor      string            `json:"git_author,omitempty"`
	TotalDurationMs int             `json:"total_duration_ms"`
	Status         string            `json:"status"`
	Steps          []traceStep       `json:"steps"`
	Metadata       map[string]interface{} `json:"metadata,omitempty"`
}

// ReportTrace pushes a completed session trace to the STOA API (fire-and-forget).
func (t *TraceReporter) ReportTrace(workerName, ticketID string, result *worker.Result, duration time.Duration) {
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		if err := t.report(ctx, workerName, ticketID, result, duration); err != nil {
			log.Printf("WARN trace report %s: %v", ticketID, err)
		}
	}()
}

func (t *TraceReporter) report(ctx context.Context, workerName, ticketID string, result *worker.Result, duration time.Duration) error {
	status := "success"
	if result.Status == "failed" || result.Status == "blocked" {
		status = "failed"
	}

	steps := []traceStep{
		{Name: "dispatched", Status: "success"},
	}
	if result.PRNumber > 0 {
		steps = append(steps, traceStep{Name: "pr-created", Status: "success"})
	}
	steps = append(steps, traceStep{Name: result.Status, Status: status})

	metadata := map[string]interface{}{
		"cost_usd": result.CostUSD,
	}
	if result.FilesChanged > 0 {
		metadata["files_changed"] = result.FilesChanged
	}
	if result.PRNumber > 0 {
		metadata["pr_number"] = result.PRNumber
	}
	if result.Summary != "" {
		metadata["summary"] = result.Summary
	}

	req := traceIngestRequest{
		TriggerType:     "ai-session",
		TriggerSource:   "hegemon-" + workerName,
		TenantID:        "hegemon",
		APIName:         ticketID,
		Environment:     "production",
		GitBranch:       result.Branch,
		GitAuthor:       workerName,
		TotalDurationMs: int(duration.Milliseconds()),
		Status:          status,
		Steps:           steps,
		Metadata:        metadata,
	}

	body, err := json.Marshal(req)
	if err != nil {
		return fmt.Errorf("marshal: %w", err)
	}

	url := t.apiURL + "/v1/traces/ingest"
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("build request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("X-STOA-API-KEY", t.ingestKey)

	resp, err := t.http.Do(httpReq)
	if err != nil {
		return fmt.Errorf("post: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("status %d: %s", resp.StatusCode, string(respBody))
	}
	return nil
}
