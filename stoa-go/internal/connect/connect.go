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

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
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
	tracer             trace.Tracer
	gatewayID          string
	startTime          time.Time
	lastDiscoveredAPIs []DiscoveredAPIPayload
}

// New creates a new STOA Connect agent.
// The HTTP client is wrapped with otelhttp for automatic W3C traceparent propagation.
func New(cfg Config) *Agent {
	return &Agent{
		cfg: cfg,
		client: &http.Client{
			Timeout:   15 * time.Second,
			Transport: otelhttp.NewTransport(http.DefaultTransport),
		},
		startTime: time.Now(),
	}
}

// SetTracer sets the OpenTelemetry tracer for the agent.
func (a *Agent) SetTracer(t trace.Tracer) {
	a.tracer = t
}

// startSpan creates a new span if a tracer is configured.
func (a *Agent) startSpan(ctx context.Context, name string, attrs ...attribute.KeyValue) (context.Context, trace.Span) {
	if a.tracer == nil {
		return ctx, trace.SpanFromContext(ctx)
	}
	return a.tracer.Start(ctx, name,
		trace.WithAttributes(attrs...),
		trace.WithSpanKind(trace.SpanKindClient),
	)
}

// Register registers this agent with the Control Plane.
// Returns the assigned gateway ID.
func (a *Agent) Register(ctx context.Context, healthPort string) error {
	ctx, span := a.startSpan(ctx, "stoa-connect.register",
		attribute.String("stoa.instance_name", a.cfg.InstanceName),
		attribute.String("stoa.environment", a.cfg.Environment),
	)
	defer span.End()

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
		span.RecordError(err)
		span.SetStatus(codes.Error, "marshal failed")
		return fmt.Errorf("marshal registration: %w", err)
	}

	url := fmt.Sprintf("%s/v1/internal/gateways/register", a.cfg.ControlPlaneURL)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(data))
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "create request failed")
		return fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Gateway-Key", a.cfg.GatewayAPIKey)

	resp, err := a.client.Do(req)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "request failed")
		return fmt.Errorf("register request: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	body, _ := io.ReadAll(resp.Body)
	span.SetAttributes(attribute.Int("http.status_code", resp.StatusCode))

	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		err := fmt.Errorf("register failed (%d): %s", resp.StatusCode, string(body))
		span.RecordError(err)
		span.SetStatus(codes.Error, "registration rejected")
		return err
	}

	var result RegistrationResponse
	if err := json.Unmarshal(body, &result); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "decode failed")
		return fmt.Errorf("decode registration response: %w", err)
	}

	a.gatewayID = result.ID
	span.SetAttributes(attribute.String("stoa.gateway_id", result.ID))
	span.SetStatus(codes.Ok, "registered")
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

	ctx, span := a.startSpan(ctx, "stoa-connect.heartbeat",
		attribute.String("stoa.gateway_id", a.gatewayID),
	)
	defer span.End()

	payload := HeartbeatPayload{
		UptimeSeconds:  int(time.Since(a.startTime).Seconds()),
		RoutesCount:    a.computeRoutesCount(),
		DiscoveredAPIs: len(a.lastDiscoveredAPIs),
	}

	span.SetAttributes(
		attribute.Int("stoa.uptime_seconds", payload.UptimeSeconds),
		attribute.Int("stoa.routes_count", payload.RoutesCount),
		attribute.Int("stoa.discovered_apis", payload.DiscoveredAPIs),
	)

	data, err := json.Marshal(payload)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "marshal failed")
		return fmt.Errorf("marshal heartbeat: %w", err)
	}

	url := fmt.Sprintf("%s/v1/internal/gateways/%s/heartbeat", a.cfg.ControlPlaneURL, a.gatewayID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(data))
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "create request failed")
		return fmt.Errorf("create heartbeat request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Gateway-Key", a.cfg.GatewayAPIKey)

	resp, err := a.client.Do(req)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "request failed")
		return fmt.Errorf("heartbeat request: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	span.SetAttributes(attribute.Int("http.status_code", resp.StatusCode))

	if resp.StatusCode != http.StatusNoContent && resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		err := fmt.Errorf("heartbeat failed (%d): %s", resp.StatusCode, string(body))
		span.RecordError(err)
		span.SetStatus(codes.Error, "heartbeat rejected")
		return err
	}

	span.SetStatus(codes.Ok, "heartbeat sent")
	HeartbeatsSent.Inc()
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

	ctx, span := a.startSpan(ctx, "stoa-connect.discovery",
		attribute.String("stoa.gateway_id", a.gatewayID),
	)
	defer span.End()

	payload := DiscoveryPayload{}
	// Convert adapters.DiscoveredAPI to DiscoveredAPIPayload
	switch v := apis.(type) {
	case []DiscoveredAPIPayload:
		payload.APIs = v
	default:
		// Marshal and re-unmarshal for type conversion
		data, err := json.Marshal(apis)
		if err != nil {
			span.RecordError(err)
			span.SetStatus(codes.Error, "marshal failed")
			return fmt.Errorf("marshal discovery apis: %w", err)
		}
		if err := json.Unmarshal(data, &payload.APIs); err != nil {
			span.RecordError(err)
			span.SetStatus(codes.Error, "convert failed")
			return fmt.Errorf("convert discovery apis: %w", err)
		}
	}

	span.SetAttributes(attribute.Int("stoa.discovered_apis", len(payload.APIs)))

	data, err := json.Marshal(payload)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "marshal failed")
		return fmt.Errorf("marshal discovery payload: %w", err)
	}

	url := fmt.Sprintf("%s/v1/internal/gateways/%s/discovery", a.cfg.ControlPlaneURL, a.gatewayID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(data))
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "create request failed")
		return fmt.Errorf("create discovery request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Gateway-Key", a.cfg.GatewayAPIKey)

	resp, err := a.client.Do(req)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "request failed")
		return fmt.Errorf("discovery report request: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	span.SetAttributes(attribute.Int("http.status_code", resp.StatusCode))

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		err := fmt.Errorf("discovery report failed (%d): %s", resp.StatusCode, string(body))
		span.RecordError(err)
		span.SetStatus(codes.Error, "discovery rejected")
		return err
	}

	span.SetStatus(codes.Ok, "discovery reported")
	return nil
}

// computeRoutesCount computes the total number of routes from discovered APIs.
// Each path on an active API counts as one route (CAB-1916).
func (a *Agent) computeRoutesCount() int {
	count := 0
	for _, api := range a.lastDiscoveredAPIs {
		if api.IsActive {
			paths := len(api.Paths)
			if paths == 0 {
				// API with no explicit paths still counts as 1 route
				paths = 1
			}
			count += paths
		}
	}
	return count
}

// DiscoveredAPIsCount returns the count of last discovered APIs.
func (a *Agent) DiscoveredAPIsCount() int {
	return len(a.lastDiscoveredAPIs)
}
