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

	url := fmt.Sprintf("%s/v1/internal/gateways/%s/config", a.cfg.ControlPlaneURL, a.gatewayID)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("create config request: %w", err)
	}
	req.Header.Set("X-Gateway-Key", a.cfg.GatewayAPIKey)

	resp, err := a.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("config request: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("config request failed (%d): %s", resp.StatusCode, string(body))
	}

	var config GatewayConfigResponse
	if err := json.Unmarshal(body, &config); err != nil {
		return nil, fmt.Errorf("decode config response: %w", err)
	}

	return &config, nil
}

// ReportSyncAck sends policy sync results to the CP.
func (a *Agent) ReportSyncAck(ctx context.Context, results []SyncedPolicyResult) error {
	if a.gatewayID == "" {
		return fmt.Errorf("not registered")
	}

	payload := SyncAckPayload{
		SyncedPolicies: results,
		SyncTimestamp:  time.Now().UTC().Format(time.RFC3339),
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal sync-ack: %w", err)
	}

	url := fmt.Sprintf("%s/v1/internal/gateways/%s/sync-ack", a.cfg.ControlPlaneURL, a.gatewayID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(data))
	if err != nil {
		return fmt.Errorf("create sync-ack request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Gateway-Key", a.cfg.GatewayAPIKey)

	resp, err := a.client.Do(req)
	if err != nil {
		return fmt.Errorf("sync-ack request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("sync-ack failed (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// RunSync performs a single policy sync cycle: fetch config → apply/remove → ack.
func (a *Agent) RunSync(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string) {
	config, err := a.FetchConfig(ctx)
	if err != nil {
		log.Printf("sync: fetch config error: %v", err)
		return
	}

	if len(config.PendingPolicies) == 0 {
		log.Println("sync: no pending policies")
		return
	}

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

	// Report sync results to CP
	if err := a.ReportSyncAck(ctx, results); err != nil {
		log.Printf("sync: report ack error: %v", err)
	}
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
