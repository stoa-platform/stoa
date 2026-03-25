package connect

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// SyncConfig holds configuration for the policy sync loop.
type SyncConfig struct {
	// Interval between sync cycles (default 60s).
	Interval time.Duration
}

// GatewayConfigResponse is the response from GET /v1/internal/gateways/{id}/config.
type GatewayConfigResponse struct {
	GatewayID          string           `json:"gateway_id"`
	Name               string           `json:"name"`
	Environment        string           `json:"environment"`
	TenantID           string           `json:"tenant_id"`
	PendingDeployments []interface{}    `json:"pending_deployments"`
	PendingPolicies    []PendingPolicy  `json:"pending_policies"`
}

// PendingPolicy represents a policy from the CP config endpoint.
type PendingPolicy struct {
	ID         string                 `json:"id"`
	Name       string                 `json:"name"`
	PolicyType string                 `json:"policy_type"`
	Config     map[string]interface{} `json:"config"`
	Priority   int                    `json:"priority"`
	Enabled    bool                   `json:"enabled"`
}

// SyncAckPayload is sent to POST /v1/internal/gateways/{id}/sync-ack.
type SyncAckPayload struct {
	SyncedPolicies []SyncedPolicyResult `json:"synced_policies"`
	SyncTimestamp  string               `json:"sync_timestamp"`
}

// SyncedPolicyResult reports the sync result for one policy.
type SyncedPolicyResult struct {
	PolicyID string `json:"policy_id"`
	Status   string `json:"status"` // "applied", "removed", "failed"
	Error    string `json:"error,omitempty"`
}

// FetchConfig pulls the gateway config (policies, deployments) from the CP.
func (a *Agent) FetchConfig(ctx context.Context) (*GatewayConfigResponse, error) {
	if a.gatewayID == "" {
		return nil, fmt.Errorf("not registered")
	}

	ctx, span := a.startSpan(ctx, "stoa-connect.sync.fetch-config",
		attribute.String("stoa.gateway_id", a.gatewayID),
	)
	defer span.End()

	url := fmt.Sprintf("%s/v1/internal/gateways/%s/config", a.cfg.ControlPlaneURL, a.gatewayID)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "create request failed")
		return nil, fmt.Errorf("create config request: %w", err)
	}
	req.Header.Set("X-Gateway-Key", a.cfg.GatewayAPIKey)

	resp, err := a.client.Do(req)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "request failed")
		return nil, fmt.Errorf("config request: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	body, _ := io.ReadAll(resp.Body)
	span.SetAttributes(attribute.Int("http.status_code", resp.StatusCode))

	if resp.StatusCode != http.StatusOK {
		err := fmt.Errorf("config request failed (%d): %s", resp.StatusCode, string(body))
		span.RecordError(err)
		span.SetStatus(codes.Error, "fetch config rejected")
		return nil, err
	}

	var config GatewayConfigResponse
	if err := json.Unmarshal(body, &config); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "decode failed")
		return nil, fmt.Errorf("decode config response: %w", err)
	}

	span.SetAttributes(attribute.Int("stoa.pending_policies", len(config.PendingPolicies)))
	span.SetStatus(codes.Ok, "config fetched")
	return &config, nil
}

// ReportSyncAck sends policy sync results to the CP.
func (a *Agent) ReportSyncAck(ctx context.Context, results []SyncedPolicyResult) error {
	if a.gatewayID == "" {
		return fmt.Errorf("not registered")
	}

	ctx, span := a.startSpan(ctx, "stoa-connect.sync.ack",
		attribute.String("stoa.gateway_id", a.gatewayID),
		attribute.Int("stoa.synced_policies", len(results)),
	)
	defer span.End()

	// Count results by status
	var applied, removed, failed int
	for _, r := range results {
		switch r.Status {
		case "applied":
			applied++
		case "removed":
			removed++
		case "failed":
			failed++
		}
	}
	span.SetAttributes(
		attribute.Int("stoa.policies_applied", applied),
		attribute.Int("stoa.policies_removed", removed),
		attribute.Int("stoa.policies_failed", failed),
	)

	payload := SyncAckPayload{
		SyncedPolicies: results,
		SyncTimestamp:  time.Now().UTC().Format(time.RFC3339),
	}

	data, err := json.Marshal(payload)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "marshal failed")
		return fmt.Errorf("marshal sync-ack: %w", err)
	}

	url := fmt.Sprintf("%s/v1/internal/gateways/%s/sync-ack", a.cfg.ControlPlaneURL, a.gatewayID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(data))
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "create request failed")
		return fmt.Errorf("create sync-ack request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Gateway-Key", a.cfg.GatewayAPIKey)

	resp, err := a.client.Do(req)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "request failed")
		return fmt.Errorf("sync-ack request: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	span.SetAttributes(attribute.Int("http.status_code", resp.StatusCode))

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		err := fmt.Errorf("sync-ack failed (%d): %s", resp.StatusCode, string(body))
		span.RecordError(err)
		span.SetStatus(codes.Error, "sync-ack rejected")
		return err
	}

	span.SetStatus(codes.Ok, "sync-ack sent")
	return nil
}

// RunSync performs a single policy sync cycle: fetch config → apply/remove → ack.
func (a *Agent) RunSync(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string) {
	ctx, span := a.startSpan(ctx, "stoa-connect.sync",
		attribute.String("stoa.gateway_id", a.gatewayID),
	)
	defer span.End()

	config, err := a.FetchConfig(ctx)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "fetch config failed")
		log.Printf("sync: fetch config error: %v", err)
		return
	}

	if len(config.PendingPolicies) == 0 {
		span.SetAttributes(attribute.Int("stoa.pending_policies", 0))
		log.Println("sync: no pending policies")
		return
	}

	span.SetAttributes(attribute.Int("stoa.pending_policies", len(config.PendingPolicies)))
	log.Printf("sync: %d policies to reconcile", len(config.PendingPolicies))

	var results []SyncedPolicyResult

	for _, policy := range config.PendingPolicies {
		result := SyncedPolicyResult{PolicyID: policy.ID}

		if !policy.Enabled {
			// Disabled policy → remove from gateway
			if err := adapter.RemovePolicy(ctx, adminURL, policy.Name, policy.PolicyType); err != nil {
				result.Status = "failed"
				result.Error = err.Error()
				log.Printf("sync: remove policy %s failed: %v", policy.Name, err)
			} else {
				result.Status = "removed"
				log.Printf("sync: removed policy %s (%s)", policy.Name, policy.PolicyType)
			}
		} else {
			// Enabled policy → apply to gateway
			action := adapters.PolicyAction{
				Type:   policy.PolicyType,
				Config: policy.Config,
			}
			if err := adapter.ApplyPolicy(ctx, adminURL, policy.Name, action); err != nil {
				result.Status = "failed"
				result.Error = err.Error()
				log.Printf("sync: apply policy %s failed: %v", policy.Name, err)
			} else {
				result.Status = "applied"
				log.Printf("sync: applied policy %s (%s)", policy.Name, policy.PolicyType)
			}
		}

		results = append(results, result)
	}

	// Update Prometheus metrics
	allOk := true
	for _, r := range results {
		switch r.Status {
		case "applied", "removed":
			SyncPoliciesApplied.Inc()
		case "failed":
			SyncPoliciesFailed.Inc()
			allOk = false
		}
	}
	if allOk {
		SyncStatus.Set(1)
	} else {
		SyncStatus.Set(0)
	}

	// Report sync results to CP
	if err := a.ReportSyncAck(ctx, results); err != nil {
		span.RecordError(err)
		log.Printf("sync: report ack error: %v", err)
	}

	span.SetStatus(codes.Ok, "sync cycle complete")
}

// StartSync starts a background goroutine that syncs policies at the configured interval.
func (a *Agent) StartSync(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string, cfg SyncConfig) {
	if adminURL == "" {
		log.Println("sync skipped: no gateway admin URL configured")
		return
	}

	interval := cfg.Interval
	if interval == 0 {
		interval = 60 * time.Second
	}

	log.Printf("starting policy sync loop (interval=%s)", interval)

	ticker := time.NewTicker(interval)
	go func() {
		defer ticker.Stop()
		// Run immediately on start
		a.RunSync(ctx, adapter, adminURL)
		for {
			select {
			case <-ctx.Done():
				log.Println("sync stopped")
				return
			case <-ticker.C:
				a.RunSync(ctx, adapter, adminURL)
			}
		}
	}()
}
