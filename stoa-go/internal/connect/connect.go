// Package connect implements the STOA Connect runtime — a lightweight agent
// that connects third-party API gateways to the STOA Control Plane.
//
// STOA Connect uses the same CP Registration Protocol (ADR-057) as Gateway
// and Link, with gateway_mode="connect". It registers at startup and maintains
// presence via heartbeat.
package connect

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"time"
)

// Config holds the STOA Connect agent configuration.
type Config struct {
	// ControlPlaneURL is the base URL of the CP API (e.g., "https://api.gostoa.dev").
	ControlPlaneURL string
	// GatewayAPIKey is the X-Gateway-Key for internal endpoint auth.
	GatewayAPIKey string
	// InstanceName identifies this connect agent (e.g., "kong-prod-01").
	InstanceName string
	// Environment is the deployment environment (e.g., "production").
	Environment string
	// Version is the stoa-connect binary version.
	Version string
	// HeartbeatInterval is the time between heartbeat calls (default 30s).
	HeartbeatInterval time.Duration
}

// ConfigFromEnv creates a Config from environment variables.
func ConfigFromEnv(version string) Config {
	cfg := Config{
		ControlPlaneURL:   os.Getenv("STOA_CONTROL_PLANE_URL"),
		GatewayAPIKey:     os.Getenv("STOA_GATEWAY_API_KEY"),
		InstanceName:      os.Getenv("STOA_INSTANCE_NAME"),
		Environment:       os.Getenv("STOA_ENVIRONMENT"),
		Version:           version,
		HeartbeatInterval: 30 * time.Second,
	}
	if cfg.Environment == "" {
		cfg.Environment = "production"
	}
	if cfg.InstanceName == "" {
		hostname, _ := os.Hostname()
		cfg.InstanceName = hostname
	}
	if interval := os.Getenv("STOA_HEARTBEAT_INTERVAL"); interval != "" {
		if d, err := time.ParseDuration(interval); err == nil {
			cfg.HeartbeatInterval = d
		}
	}
	return cfg
}

// RegistrationPayload is the payload sent to POST /v1/internal/gateways/register.
type RegistrationPayload struct {
	Hostname     string   `json:"hostname"`
	Mode         string   `json:"mode"`
	Version      string   `json:"version"`
	Environment  string   `json:"environment"`
	Capabilities []string `json:"capabilities"`
	AdminURL     string   `json:"admin_url"`
}

// RegistrationResponse is the response from the register endpoint.
type RegistrationResponse struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Environment string `json:"environment"`
	Status      string `json:"status"`
}

// HeartbeatPayload is the payload sent to POST /v1/internal/gateways/{id}/heartbeat.
type HeartbeatPayload struct {
	UptimeSeconds  int `json:"uptime_seconds"`
	RoutesCount    int `json:"routes_count"`
	PoliciesCount  int `json:"policies_count"`
	DiscoveredAPIs int `json:"discovered_apis"`
}

// DiscoveryPayload is the payload sent to POST /v1/internal/gateways/{id}/discovery.
type DiscoveryPayload struct {
	APIs []DiscoveredAPIPayload `json:"apis"`
}

// DiscoveredAPIPayload represents a single discovered API for the CP.
type DiscoveredAPIPayload struct {
	Name       string   `json:"name"`
	Version    string   `json:"version,omitempty"`
	BackendURL string   `json:"backend_url,omitempty"`
	Paths      []string `json:"paths,omitempty"`
	Methods    []string `json:"methods,omitempty"`
	Policies   []string `json:"policies,omitempty"`
	IsActive   bool     `json:"is_active"`
}

// Agent is the STOA Connect runtime agent.
type Agent struct {
	cfg                Config
	client             *http.Client
	gatewayID          string
	startTime          time.Time
	lastDiscoveredAPIs []DiscoveredAPIPayload
}

// New creates a new STOA Connect agent.
func New(cfg Config) *Agent {
	return &Agent{
		cfg: cfg,
		client: &http.Client{
			Timeout: 15 * time.Second,
		},
		startTime: time.Now(),
	}
}

// Register registers this agent with the Control Plane.
// Returns the assigned gateway ID.
func (a *Agent) Register(ctx context.Context, healthPort string) error {
	payload := RegistrationPayload{
		Hostname:     a.cfg.InstanceName,
		Mode:         "connect",
		Version:      a.cfg.Version,
		Environment:  a.cfg.Environment,
		Capabilities: []string{"policy_sync", "health_monitoring"},
		AdminURL:     fmt.Sprintf("http://%s:%s", a.cfg.InstanceName, healthPort),
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal registration: %w", err)
	}

	url := fmt.Sprintf("%s/v1/internal/gateways/register", a.cfg.ControlPlaneURL)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(data))
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Gateway-Key", a.cfg.GatewayAPIKey)

	resp, err := a.client.Do(req)
	if err != nil {
		return fmt.Errorf("register request: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		return fmt.Errorf("register failed (%d): %s", resp.StatusCode, string(body))
	}

	var result RegistrationResponse
	if err := json.Unmarshal(body, &result); err != nil {
		return fmt.Errorf("decode registration response: %w", err)
	}

	a.gatewayID = result.ID
	log.Printf("registered with CP: id=%s name=%s", result.ID, result.Name)
	return nil
}

// GatewayID returns the assigned gateway ID after registration.
func (a *Agent) GatewayID() string {
	return a.gatewayID
}

// Heartbeat sends a single heartbeat to the Control Plane.
func (a *Agent) Heartbeat(ctx context.Context) error {
	if a.gatewayID == "" {
		return fmt.Errorf("not registered")
	}

	payload := HeartbeatPayload{
		UptimeSeconds:  int(time.Since(a.startTime).Seconds()),
		DiscoveredAPIs: len(a.lastDiscoveredAPIs),
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal heartbeat: %w", err)
	}

	url := fmt.Sprintf("%s/v1/internal/gateways/%s/heartbeat", a.cfg.ControlPlaneURL, a.gatewayID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(data))
	if err != nil {
		return fmt.Errorf("create heartbeat request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Gateway-Key", a.cfg.GatewayAPIKey)

	resp, err := a.client.Do(req)
	if err != nil {
		return fmt.Errorf("heartbeat request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusNoContent && resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("heartbeat failed (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// StartHeartbeat starts a background goroutine that sends heartbeats
// at the configured interval. Stops when ctx is cancelled.
func (a *Agent) StartHeartbeat(ctx context.Context) {
	ticker := time.NewTicker(a.cfg.HeartbeatInterval)
	go func() {
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				log.Println("heartbeat stopped")
				return
			case <-ticker.C:
				if err := a.Heartbeat(ctx); err != nil {
					log.Printf("heartbeat error: %v", err)
				}
			}
		}
	}()
}

// IsConfigured returns true if the agent has enough config to register.
func (a *Agent) IsConfigured() bool {
	return a.cfg.ControlPlaneURL != "" && a.cfg.GatewayAPIKey != ""
}

// ReportDiscovery sends discovered APIs to the Control Plane.
func (a *Agent) ReportDiscovery(ctx context.Context, apis interface{}) error {
	if a.gatewayID == "" {
		return fmt.Errorf("not registered")
	}

	payload := DiscoveryPayload{}
	// Convert adapters.DiscoveredAPI to DiscoveredAPIPayload
	switch v := apis.(type) {
	case []DiscoveredAPIPayload:
		payload.APIs = v
	default:
		// Marshal and re-unmarshal for type conversion
		data, err := json.Marshal(apis)
		if err != nil {
			return fmt.Errorf("marshal discovery apis: %w", err)
		}
		if err := json.Unmarshal(data, &payload.APIs); err != nil {
			return fmt.Errorf("convert discovery apis: %w", err)
		}
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal discovery payload: %w", err)
	}

	url := fmt.Sprintf("%s/v1/internal/gateways/%s/discovery", a.cfg.ControlPlaneURL, a.gatewayID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(data))
	if err != nil {
		return fmt.Errorf("create discovery request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Gateway-Key", a.cfg.GatewayAPIKey)

	resp, err := a.client.Do(req)
	if err != nil {
		return fmt.Errorf("discovery report request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("discovery report failed (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// DiscoveredAPIsCount returns the count of last discovered APIs.
func (a *Agent) DiscoveredAPIsCount() int {
	return len(a.lastDiscoveredAPIs)
}
