package worker

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// GatewayClient provides HTTP access to STOA Gateway budget and claims APIs.
// Shares the TokenCache with GatewayExecutor for efficient token reuse.
type GatewayClient struct {
	baseURL    string
	tokenCache *TokenCache
	http       *http.Client
}

// NewGatewayClient creates a client for gateway budget and claims operations.
func NewGatewayClient(baseURL string, tokenCache *TokenCache) *GatewayClient {
	return &GatewayClient{
		baseURL:    baseURL,
		tokenCache: tokenCache,
		http:       &http.Client{Timeout: 10 * time.Second},
	}
}

// --- Budget Operations (CAB-1717) ---

// BudgetStatus represents the response from the gateway budget check endpoint.
type BudgetStatus struct {
	Allowed    bool    `json:"allowed"`
	DailyCost  float64 `json:"daily_cost"`
	DailyLimit float64 `json:"daily_limit"`
	Reason     string  `json:"reason,omitempty"`
}

// CheckBudget queries the gateway to determine if the agent has budget remaining.
func (c *GatewayClient) CheckBudget(ctx context.Context, agentName string) (*BudgetStatus, error) {
	url := fmt.Sprintf("%s/hegemon/budget/%s", c.baseURL, agentName)

	resp, err := c.doRequest(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("budget check: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read budget response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("budget check returned %d: %s", resp.StatusCode, string(body))
	}

	var status BudgetStatus
	if err := json.Unmarshal(body, &status); err != nil {
		return nil, fmt.Errorf("parse budget response: %w", err)
	}
	return &status, nil
}

// costRecord is the payload for POST /hegemon/budget/{agent}/cost.
type costRecord struct {
	CostUSD    float64 `json:"cost_usd"`
	DispatchID string  `json:"dispatch_id,omitempty"`
}

// RecordCost reports execution cost to the gateway for centralized tracking.
func (c *GatewayClient) RecordCost(ctx context.Context, agentName string, costUSD float64) error {
	url := fmt.Sprintf("%s/hegemon/budget/%s/cost", c.baseURL, agentName)

	payload, err := json.Marshal(costRecord{CostUSD: costUSD})
	if err != nil {
		return fmt.Errorf("marshal cost record: %w", err)
	}

	resp, err := c.doRequest(ctx, http.MethodPost, url, payload)
	if err != nil {
		return fmt.Errorf("record cost: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusAccepted && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("record cost returned %d: %s", resp.StatusCode, string(body))
	}
	return nil
}

// --- Claims Operations (CAB-1719) ---

// claimRequest is the payload for POST /hegemon/claims/{mega_id}/reserve.
type claimRequest struct {
	Owner string `json:"owner"`
}

// ErrClaimConflict indicates another worker already owns the claim (HTTP 409).
var ErrClaimConflict = fmt.Errorf("claim conflict: already owned by another worker")

// ReserveClaim attempts to reserve a MEGA phase for the given owner.
// Returns ErrClaimConflict if another worker already owns the phase (409).
func (c *GatewayClient) ReserveClaim(ctx context.Context, megaID, owner string) error {
	url := fmt.Sprintf("%s/hegemon/claims/%s/reserve", c.baseURL, megaID)

	payload, err := json.Marshal(claimRequest{Owner: owner})
	if err != nil {
		return fmt.Errorf("marshal claim request: %w", err)
	}

	resp, err := c.doRequest(ctx, http.MethodPost, url, payload)
	if err != nil {
		return fmt.Errorf("reserve claim: %w", err)
	}
	defer resp.Body.Close()

	switch resp.StatusCode {
	case http.StatusOK, http.StatusCreated:
		return nil
	case http.StatusConflict:
		return ErrClaimConflict
	default:
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("reserve claim returned %d: %s", resp.StatusCode, string(body))
	}
}

// ReleaseClaim releases a MEGA phase claim.
func (c *GatewayClient) ReleaseClaim(ctx context.Context, megaID, owner string) error {
	url := fmt.Sprintf("%s/hegemon/claims/%s/release", c.baseURL, megaID)

	payload, err := json.Marshal(claimRequest{Owner: owner})
	if err != nil {
		return fmt.Errorf("marshal release request: %w", err)
	}

	resp, err := c.doRequest(ctx, http.MethodPost, url, payload)
	if err != nil {
		return fmt.Errorf("release claim: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("release claim returned %d: %s", resp.StatusCode, string(body))
	}
	return nil
}

// Heartbeat sends a keepalive for an active claim to prevent stale detection.
func (c *GatewayClient) Heartbeat(ctx context.Context, megaID, owner string) error {
	url := fmt.Sprintf("%s/hegemon/claims/%s/heartbeat", c.baseURL, megaID)

	payload, err := json.Marshal(claimRequest{Owner: owner})
	if err != nil {
		return fmt.Errorf("marshal heartbeat request: %w", err)
	}

	resp, err := c.doRequest(ctx, http.MethodPost, url, payload)
	if err != nil {
		return fmt.Errorf("heartbeat: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("heartbeat returned %d: %s", resp.StatusCode, string(body))
	}
	return nil
}

// --- Shared HTTP helper ---

func (c *GatewayClient) doRequest(ctx context.Context, method, url string, body []byte) (*http.Response, error) {
	token, err := c.tokenCache.Token(ctx)
	if err != nil {
		return nil, fmt.Errorf("auth: %w", err)
	}

	var bodyReader io.Reader
	if body != nil {
		bodyReader = bytes.NewReader(body)
	}

	req, err := http.NewRequestWithContext(ctx, method, url, bodyReader)
	if err != nil {
		return nil, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	return c.http.Do(req)
}
