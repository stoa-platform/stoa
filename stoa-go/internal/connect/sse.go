package connect

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// SSEConfig holds configuration for the SSE deployment stream (ADR-059).
type SSEConfig struct {
	// Enabled toggles SSE mode (replaces route polling when true).
	Enabled bool
	// ReconnectInterval is the delay before reconnecting after a stream drop.
	ReconnectInterval time.Duration
	// MaxReconnectInterval caps exponential backoff.
	MaxReconnectInterval time.Duration
}

// SSEConfigFromEnv creates an SSEConfig from environment variables.
func SSEConfigFromEnv() SSEConfig {
	cfg := SSEConfig{
		Enabled:              os.Getenv("STOA_SSE_ENABLED") == "true",
		ReconnectInterval:    2 * time.Second,
		MaxReconnectInterval: 60 * time.Second,
	}
	if d := os.Getenv("STOA_SSE_RECONNECT_INTERVAL"); d != "" {
		if parsed, err := time.ParseDuration(d); err == nil {
			cfg.ReconnectInterval = parsed
		}
	}
	return cfg
}

// SSEEvent represents a parsed Server-Sent Event.
type SSEEvent struct {
	Event string          `json:"event"`
	Data  json.RawMessage `json:"data"`
}

// DeploymentEvent is the data payload for a sync-deployment SSE event.
type DeploymentEvent struct {
	DeploymentID      string          `json:"deployment_id"`
	APICatalogID      string          `json:"api_catalog_id"`
	GatewayInstanceID string          `json:"gateway_instance_id"`
	SyncStatus        string          `json:"sync_status"`
	DesiredState      json.RawMessage `json:"desired_state"`
}

// StartDeploymentStream starts an SSE listener for real-time deployment events (ADR-059).
// On each event, it syncs the route to the local gateway and reports back via route-sync-ack.
// On disconnect, it catches up via FetchRoutes() then resumes SSE.
func (a *Agent) StartDeploymentStream(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string, cfg SSEConfig) {
	if a.gatewayID == "" {
		log.Println("sse-stream skipped: not registered with CP")
		return
	}
	if adminURL == "" {
		log.Println("sse-stream skipped: no gateway admin URL configured")
		return
	}

	log.Printf("starting SSE deployment stream (reconnect=%s)", cfg.ReconnectInterval)

	go func() {
		backoff := cfg.ReconnectInterval

		for {
			select {
			case <-ctx.Done():
				log.Println("sse-stream stopped")
				return
			default:
			}

			// Catch up on any missed deployments before streaming
			a.RunRouteSync(ctx, adapter, adminURL)

			err := a.streamEvents(ctx, adapter, adminURL)
			if err != nil && ctx.Err() == nil {
				log.Printf("sse-stream: connection lost: %v (reconnecting in %s)", err, backoff)
				select {
				case <-ctx.Done():
					return
				case <-time.After(backoff):
				}
				// Exponential backoff capped at max
				backoff = backoff * 2
				if backoff > cfg.MaxReconnectInterval {
					backoff = cfg.MaxReconnectInterval
				}
			} else {
				// Reset backoff on clean disconnect
				backoff = cfg.ReconnectInterval
			}
		}
	}()
}

// streamEvents connects to the SSE endpoint and processes events until the stream drops.
func (a *Agent) streamEvents(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string) error {
	ctx, span := a.startSpan(ctx, "stoa-connect.sse.stream",
		attribute.String("stoa.gateway_id", a.gatewayID),
	)
	defer span.End()

	url := fmt.Sprintf("%s/v1/internal/gateways/%s/events", a.cfg.ControlPlaneURL, a.gatewayID)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		span.RecordError(err)
		return fmt.Errorf("create SSE request: %w", err)
	}
	req.Header.Set("X-Gateway-Key", a.cfg.GatewayAPIKey)
	req.Header.Set("Accept", "text/event-stream")
	req.Header.Set("Cache-Control", "no-cache")

	// Use a separate client without timeout for long-lived SSE connections
	sseClient := &http.Client{Transport: a.client.Transport}
	resp, err := sseClient.Do(req)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "SSE connect failed")
		return fmt.Errorf("SSE connect: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		span.SetStatus(codes.Error, "SSE rejected")
		return fmt.Errorf("SSE endpoint returned %d", resp.StatusCode)
	}

	log.Printf("sse-stream: connected to %s", url)
	span.SetStatus(codes.Ok, "connected")

	scanner := bufio.NewScanner(resp.Body)
	var eventType string
	var dataLines []string

	for scanner.Scan() {
		line := scanner.Text()

		if line == "" {
			// Empty line = end of event
			if eventType != "" && len(dataLines) > 0 {
				data := strings.Join(dataLines, "\n")
				a.handleSSEEvent(ctx, adapter, adminURL, eventType, []byte(data))
			}
			eventType = ""
			dataLines = nil
			continue
		}

		if strings.HasPrefix(line, "event:") {
			eventType = strings.TrimSpace(strings.TrimPrefix(line, "event:"))
		} else if strings.HasPrefix(line, "data:") {
			dataLines = append(dataLines, strings.TrimSpace(strings.TrimPrefix(line, "data:")))
		}
		// Ignore "id:", "retry:", comments (":")
	}

	if err := scanner.Err(); err != nil {
		return fmt.Errorf("SSE read: %w", err)
	}

	return fmt.Errorf("SSE stream ended")
}

// handleSSEEvent processes a single SSE event.
func (a *Agent) handleSSEEvent(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string, eventType string, data []byte) {
	switch eventType {
	case "sync-deployment":
		a.handleSyncDeployment(ctx, adapter, adminURL, data)
	case "heartbeat":
		// Keepalive — ignore
	default:
		log.Printf("sse-stream: unknown event type %q", eventType)
	}
}

// handleSyncDeployment processes a sync-deployment event by applying the route and acking.
func (a *Agent) handleSyncDeployment(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string, data []byte) {
	ctx, span := a.startSpan(ctx, "stoa-connect.sse.sync-deployment",
		attribute.String("stoa.gateway_id", a.gatewayID),
	)
	defer span.End()

	var steps []SyncStep

	// Step: agent_received — SSE event consumed
	steps = append(steps, newSyncStep("agent_received", "success", ""))

	var event DeploymentEvent
	if err := json.Unmarshal(data, &event); err != nil {
		log.Printf("sse-stream: decode deployment event error: %v", err)
		span.RecordError(err)
		return
	}

	span.SetAttributes(attribute.String("stoa.deployment_id", event.DeploymentID))
	log.Printf("sse-stream: received deployment %s (status=%s)", event.DeploymentID, event.SyncStatus)

	// Step: adapter_connected — gateway adapter ready
	steps = append(steps, newSyncStep("adapter_connected", "success", ""))

	// Parse desired_state into a Route for the adapter
	var route adapters.Route
	if err := json.Unmarshal(event.DesiredState, &route); err != nil {
		log.Printf("sse-stream: decode desired_state error: %v", err)
		span.RecordError(err)
		steps = append(steps, newSyncStep("api_synced", "failed", fmt.Sprintf("decode desired_state: %v", err)))
		a.reportDeploymentResultWithSteps(ctx, event.DeploymentID, "failed", fmt.Sprintf("decode desired_state: %v", err), steps)
		return
	}
	route.DeploymentID = event.DeploymentID

	// Apply to gateway — Step: api_synced
	syncErr := adapter.SyncRoutes(ctx, adminURL, []adapters.Route{route})

	status := "applied"
	errMsg := ""
	if syncErr != nil {
		status = "failed"
		errMsg = syncErr.Error()
		span.RecordError(syncErr)
		span.SetStatus(codes.Error, "sync failed")
		log.Printf("sse-stream: sync deployment %s failed: %v", event.DeploymentID, syncErr)
		steps = append(steps, newSyncStep("api_synced", "failed", syncErr.Error()))
	} else {
		span.SetStatus(codes.Ok, "synced")
		log.Printf("sse-stream: sync deployment %s applied", event.DeploymentID)
		steps = append(steps, newSyncStep("api_synced", "success", ""))
	}

	a.reportDeploymentResultWithSteps(ctx, event.DeploymentID, status, errMsg, steps)
}

// reportDeploymentResultWithSteps sends a single deployment ack with step trace via route-sync-ack.
func (a *Agent) reportDeploymentResultWithSteps(ctx context.Context, deploymentID, status, errMsg string, steps []SyncStep) {
	result := SyncedRouteResult{
		DeploymentID: deploymentID,
		Status:       status,
		Error:        errMsg,
		Steps:        steps,
	}
	if ackErr := a.ReportRouteSyncAck(ctx, []SyncedRouteResult{result}); ackErr != nil {
		log.Printf("sse-stream: ack error for %s: %v", deploymentID, ackErr)
	}
}
