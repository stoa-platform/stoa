package worker

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/stoa-platform/stoa/hegemon/daemon/internal/config"
)

// GatewayExecutor dispatches tickets to workers via the STOA Gateway HTTP API
// instead of SSH. Implements the same Result contract as the SSH Executor.
type GatewayExecutor struct {
	gatewayURL   string
	tokenCache   *TokenCache
	httpClient   *http.Client
	pollInterval time.Duration // polling interval for dispatch status (default: 15s)
}

// TokenCache holds a Keycloak access token with expiry, refreshed via client_credentials.
type TokenCache struct {
	mu        sync.Mutex
	token     string
	expiresAt time.Time

	keycloakURL  string
	clientID     string
	clientSecret string
	realm        string
}

// NewTokenCache creates a token cache for client_credentials flow.
func NewTokenCache(keycloakURL, clientID, clientSecret string) *TokenCache {
	return &TokenCache{
		keycloakURL:  keycloakURL,
		clientID:     clientID,
		clientSecret: clientSecret,
		realm:        "stoa",
	}
}

// Token returns a valid access token, refreshing if needed.
func (tc *TokenCache) Token(ctx context.Context) (string, error) {
	tc.mu.Lock()
	defer tc.mu.Unlock()

	// Return cached token if still valid (with 30s buffer).
	if tc.token != "" && time.Now().Add(30*time.Second).Before(tc.expiresAt) {
		return tc.token, nil
	}

	token, expiresIn, err := tc.fetchToken(ctx)
	if err != nil {
		return "", err
	}
	tc.token = token
	tc.expiresAt = time.Now().Add(time.Duration(expiresIn) * time.Second)
	return tc.token, nil
}

type tokenResponse struct {
	AccessToken string `json:"access_token"`
	ExpiresIn   int    `json:"expires_in"`
	TokenType   string `json:"token_type"`
	Error       string `json:"error,omitempty"`
	ErrorDesc   string `json:"error_description,omitempty"`
}

func (tc *TokenCache) fetchToken(ctx context.Context) (string, int, error) {
	tokenURL := fmt.Sprintf("%s/realms/%s/protocol/openid-connect/token", tc.keycloakURL, tc.realm)

	body := fmt.Sprintf("grant_type=client_credentials&client_id=%s&client_secret=%s",
		tc.clientID, tc.clientSecret)

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, tokenURL, bytes.NewBufferString(body))
	if err != nil {
		return "", 0, fmt.Errorf("build token request: %w", err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", 0, fmt.Errorf("token request: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", 0, fmt.Errorf("read token response: %w", err)
	}

	var tr tokenResponse
	if err := json.Unmarshal(respBody, &tr); err != nil {
		return "", 0, fmt.Errorf("parse token response: %w", err)
	}
	if tr.Error != "" {
		return "", 0, fmt.Errorf("token error: %s — %s", tr.Error, tr.ErrorDesc)
	}
	if tr.AccessToken == "" {
		return "", 0, fmt.Errorf("empty access token in response")
	}
	return tr.AccessToken, tr.ExpiresIn, nil
}

// NewGatewayExecutor creates an HTTP-based executor using the STOA Gateway.
func NewGatewayExecutor(cfg config.GatewayConfig) *GatewayExecutor {
	return &GatewayExecutor{
		gatewayURL:   cfg.URL,
		tokenCache:   NewTokenCache(cfg.KeycloakURL, cfg.ClientID, cfg.ClientSecret),
		httpClient:   &http.Client{Timeout: 30 * time.Second},
		pollInterval: 15 * time.Second,
	}
}

// TokenCache returns the shared token cache for reuse by GatewayClient.
func (g *GatewayExecutor) TokenCache() *TokenCache {
	return g.tokenCache
}

// dispatchRequest is the payload sent to POST /hegemon/dispatch.
type dispatchRequest struct {
	TicketID    string `json:"ticket_id"`
	Title       string `json:"title"`
	Description string `json:"description"`
	Estimate    int    `json:"estimate"`
	WorkerName  string `json:"worker_name"`
}

// dispatchResponse is returned by POST /hegemon/dispatch.
type dispatchResponse struct {
	DispatchID string `json:"dispatch_id"`
	Status     string `json:"status"` // "accepted", "rejected"
	Reason     string `json:"reason,omitempty"`
}

// dispatchStatusResponse is returned by GET /hegemon/dispatch/{id}.
type dispatchStatusResponse struct {
	DispatchID string  `json:"dispatch_id"`
	Status     string  `json:"status"` // "running", "completed", "failed", "blocked"
	Result     *Result `json:"result,omitempty"`
	Raw        string  `json:"raw,omitempty"`
}

// Execute dispatches a ticket via the gateway HTTP API and polls for completion.
func (g *GatewayExecutor) Execute(ctx context.Context, w *config.WorkerConfig, ticketID, title, description string, estimate int, timeout time.Duration) (*Result, string, error) {
	token, err := g.tokenCache.Token(ctx)
	if err != nil {
		return nil, "", fmt.Errorf("gateway auth: %w", err)
	}

	// POST /hegemon/dispatch
	payload := dispatchRequest{
		TicketID:    ticketID,
		Title:       title,
		Description: description,
		Estimate:    estimate,
		WorkerName:  w.Name,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, "", fmt.Errorf("marshal dispatch request: %w", err)
	}

	dispatchURL := fmt.Sprintf("%s/hegemon/dispatch", g.gatewayURL)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, dispatchURL, bytes.NewReader(body))
	if err != nil {
		return nil, "", fmt.Errorf("build dispatch request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)

	resp, err := g.httpClient.Do(req)
	if err != nil {
		return nil, "", fmt.Errorf("dispatch request: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, "", fmt.Errorf("read dispatch response: %w", err)
	}

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusAccepted {
		return nil, string(respBody), fmt.Errorf("gateway dispatch returned %d: %s", resp.StatusCode, string(respBody))
	}

	var dr dispatchResponse
	if err := json.Unmarshal(respBody, &dr); err != nil {
		return nil, string(respBody), fmt.Errorf("parse dispatch response: %w", err)
	}
	if dr.Status == "rejected" {
		return &Result{Status: "failed", Summary: fmt.Sprintf("gateway rejected: %s", dr.Reason)}, "", nil
	}

	log.Printf("Gateway dispatch accepted: %s (dispatch_id=%s)", ticketID, dr.DispatchID)

	// Poll for completion.
	return g.pollStatus(ctx, dr.DispatchID, timeout)
}

func (g *GatewayExecutor) pollStatus(ctx context.Context, dispatchID string, timeout time.Duration) (*Result, string, error) {
	pollInterval := g.pollInterval
	deadline := time.After(timeout)
	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()

	statusURL := fmt.Sprintf("%s/hegemon/dispatch/%s", g.gatewayURL, dispatchID)

	for {
		select {
		case <-ctx.Done():
			return nil, "", fmt.Errorf("context cancelled while polling dispatch %s", dispatchID)
		case <-deadline:
			return nil, "", fmt.Errorf("timeout polling dispatch %s after %s", dispatchID, timeout)
		case <-ticker.C:
			token, err := g.tokenCache.Token(ctx)
			if err != nil {
				log.Printf("WARN: token refresh during poll: %v", err)
				continue
			}

			req, err := http.NewRequestWithContext(ctx, http.MethodGet, statusURL, nil)
			if err != nil {
				continue
			}
			req.Header.Set("Authorization", "Bearer "+token)

			resp, err := g.httpClient.Do(req)
			if err != nil {
				log.Printf("WARN: poll dispatch %s: %v", dispatchID, err)
				continue
			}

			body, _ := io.ReadAll(resp.Body)
			resp.Body.Close()

			if resp.StatusCode != http.StatusOK {
				log.Printf("WARN: poll dispatch %s returned %d", dispatchID, resp.StatusCode)
				continue
			}

			var status dispatchStatusResponse
			if err := json.Unmarshal(body, &status); err != nil {
				log.Printf("WARN: parse poll response: %v", err)
				continue
			}

			switch status.Status {
			case "completed", "failed", "blocked":
				if status.Result != nil {
					return status.Result, status.Raw, nil
				}
				return &Result{Status: status.Status, Summary: "completed via gateway"}, status.Raw, nil
			case "running":
				// Continue polling.
			default:
				log.Printf("WARN: unknown dispatch status: %s", status.Status)
			}
		}
	}
}
