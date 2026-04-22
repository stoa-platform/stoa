// Package connect implements the STOA Connect runtime — a lightweight agent
// that connects third-party API gateways to the STOA Control Plane.
//
// STOA Connect uses the same CP Registration Protocol (ADR-057) as Gateway
// and Link, with gateway_mode="connect". It registers at startup and maintains
// presence via heartbeat.
package connect

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel/attribute"
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
	// TargetGatewayURL is the URL of the third-party gateway managed by this agent.
	TargetGatewayURL string
	// PublicURL is the public DNS URL where runtime APIs are served.
	PublicURL string
	// UIURL is the web UI URL of the third-party gateway admin console.
	UIURL string
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
	cfg.TargetGatewayURL = os.Getenv("STOA_TARGET_GATEWAY_URL")
	cfg.PublicURL = os.Getenv("STOA_PUBLIC_URL")
	cfg.UIURL = os.Getenv("STOA_UI_URL")
	return cfg
}

// Agent is the STOA Connect runtime agent.
//
// Mutable runtime state (gatewayID, discovered APIs) lives under Agent.state
// behind a RWMutex — safe for concurrent access from the heartbeat, discovery,
// sync, SSE and /health goroutines.
//
// Fields set once before any loop goroutine starts (cfg, cp, transport, tracer,
// startTime; healthPort — written in the first Register call from main
// goroutine) are kept on Agent without locking; happens-before is guaranteed
// by the `go` statement that later launches the loops.
type Agent struct {
	cfg        Config
	cp         *cpClient         // CP HTTP client; 7 endpoints delegated here
	transport  http.RoundTripper // otelhttp-wrapped; shared with SSE stream
	tracer     trace.Tracer      // used for business spans that live on the Agent (RunSync etc.)
	state      *agentState
	healthPort string // set in the first Register; read from the heartbeat loop on re-register
	startTime  time.Time
}

// New creates a new STOA Connect agent.
// The HTTP transport is wrapped with otelhttp for automatic W3C traceparent
// propagation and is shared between the CP client and the SSE stream.
func New(cfg Config) *Agent {
	transport := otelhttp.NewTransport(http.DefaultTransport)
	return &Agent{
		cfg:       cfg,
		cp:        newCPClient(cfg.ControlPlaneURL, cfg.GatewayAPIKey, transport),
		transport: transport,
		state:     newAgentState(),
		startTime: time.Now(),
	}
}

// SetTracer sets the OpenTelemetry tracer for the agent. Propagates to the
// CP client so every stoa-connect.<action> span uses the same tracer.
func (a *Agent) SetTracer(t trace.Tracer) {
	a.tracer = t
	a.cp.SetTracer(t)
}

// startSpan creates a new span on the Agent's tracer if one is configured.
// Used for orchestration-level spans (RunSync, RunRouteSync, SSE handlers);
// transport-level spans live on the cpClient.
func (a *Agent) startSpan(ctx context.Context, name string, attrs ...attribute.KeyValue) (context.Context, trace.Span) {
	if a.tracer == nil {
		return ctx, trace.SpanFromContext(ctx)
	}
	return a.tracer.Start(ctx, name,
		trace.WithAttributes(attrs...),
		trace.WithSpanKind(trace.SpanKindClient),
	)
}

// Register registers this agent with the Control Plane and records the
// assigned gateway ID plus the local healthPort on success (for later
// re-registration).
func (a *Agent) Register(ctx context.Context, healthPort string) error {
	payload := RegistrationPayload{
		Hostname:         a.cfg.InstanceName,
		Mode:             "connect",
		Version:          a.cfg.Version,
		Environment:      a.cfg.Environment,
		Capabilities:     []string{"policy_sync", "health_monitoring"},
		AdminURL:         fmt.Sprintf("http://%s:%s", a.cfg.InstanceName, healthPort),
		TargetGatewayURL: a.cfg.TargetGatewayURL,
		PublicURL:        a.cfg.PublicURL,
		UIURL:            a.cfg.UIURL,
	}

	result, err := a.cp.Register(ctx, payload)
	if err != nil {
		return err
	}

	a.state.SetGatewayID(result.ID)
	a.healthPort = healthPort
	log.Printf("registered with CP: id=%s name=%s", result.ID, result.Name)
	return nil
}

// GatewayID returns the assigned gateway ID after registration.
func (a *Agent) GatewayID() string {
	return a.state.GatewayID()
}

// Heartbeat sends a single heartbeat to the Control Plane.
// Returns ErrNotRegistered if called before Register, ErrGatewayNotFound if
// the CP responds 404 (gateway purged).
func (a *Agent) Heartbeat(ctx context.Context) error {
	gatewayID := a.state.GatewayID()
	if gatewayID == "" {
		return ErrNotRegistered
	}

	payload := HeartbeatPayload{
		UptimeSeconds:  int(time.Since(a.startTime).Seconds()),
		RoutesCount:    a.state.ComputeRoutesCount(),
		DiscoveredAPIs: a.state.DiscoveredAPIsCount(),
	}

	if err := a.cp.Heartbeat(ctx, gatewayID, payload); err != nil {
		return err
	}
	HeartbeatsSent.Inc()
	return nil
}

// reRegisterThreshold is the number of consecutive 404 heartbeats before the
// agent auto-re-registers with the Control Plane. Chosen conservatively to avoid
// thrashing on transient CP outages; do not tune without validating CP-side
// expectations (ADR-057).
const reRegisterThreshold = 3

// StartHeartbeat starts a background goroutine that sends heartbeats
// at the configured interval. If the CP responds 404 (gateway purged),
// it re-registers automatically after reRegisterThreshold consecutive 404s.
// Stops when ctx is cancelled.
func (a *Agent) StartHeartbeat(ctx context.Context) {
	ticker := time.NewTicker(a.cfg.HeartbeatInterval)
	go func() {
		defer ticker.Stop()
		consecutiveNotFound := 0
		for {
			select {
			case <-ctx.Done():
				log.Println("heartbeat stopped")
				return
			case <-ticker.C:
				if err := a.Heartbeat(ctx); err != nil {
					if errors.Is(err, ErrGatewayNotFound) {
						consecutiveNotFound++
						log.Printf("heartbeat 404 (%d/%d) — gateway not found on CP",
							consecutiveNotFound, reRegisterThreshold)
						if consecutiveNotFound >= reRegisterThreshold {
							log.Println("gateway purged from CP, re-registering...")
							a.state.ClearGatewayID()
							if regErr := a.Register(ctx, a.healthPort); regErr != nil {
								log.Printf("re-registration failed: %v", regErr)
							} else {
								log.Printf("re-registered with CP: id=%s", a.state.GatewayID())
								consecutiveNotFound = 0
							}
						}
					} else {
						log.Printf("heartbeat error: %v", err)
					}
				} else {
					consecutiveNotFound = 0
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
func (a *Agent) ReportDiscovery(ctx context.Context, apis []DiscoveredAPIPayload) error {
	gatewayID := a.state.GatewayID()
	if gatewayID == "" {
		return ErrNotRegistered
	}
	return a.cp.ReportDiscovery(ctx, gatewayID, DiscoveryPayload{APIs: apis})
}

// DiscoveredAPIsCount returns the count of last discovered APIs.
func (a *Agent) DiscoveredAPIsCount() int {
	return a.state.DiscoveredAPIsCount()
}
