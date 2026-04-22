package connect

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// cpClient is the HTTP client for calls to the Control Plane.
//
// It owns a single http.Client (15s timeout) built on a shared otelhttp-wrapped
// transport so W3C traceparent propagation is consistent. The baseURL + apiKey
// are injected once at construction — the 7 methods below take the gatewayID
// as an argument instead of reading it from state, so the client holds no
// mutable runtime state.
//
// Each method emits one business-level span named "stoa-connect.<action>" on
// top of the auto span emitted by otelhttp, so traces show both the HTTP
// transport and the connect-specific semantics.
type cpClient struct {
	http    *http.Client
	tracer  trace.Tracer // may be nil before SetTracer
	baseURL string
	apiKey  string
}

// newCPClient wires the shared transport into an http.Client with the standard
// 15s timeout used for all CP requests. The transport is also used by the SSE
// stream (no timeout) via Agent.transport — both share it for otelhttp
// consistency.
func newCPClient(baseURL, apiKey string, transport http.RoundTripper) *cpClient {
	return &cpClient{
		http: &http.Client{
			Timeout:   15 * time.Second,
			Transport: transport,
		},
		baseURL: baseURL,
		apiKey:  apiKey,
	}
}

// SetTracer installs the OpenTelemetry tracer used for business spans.
// Intended to be called from the main goroutine before any loop starts.
func (c *cpClient) SetTracer(t trace.Tracer) {
	c.tracer = t
}

func (c *cpClient) startSpan(ctx context.Context, name string, attrs ...attribute.KeyValue) (context.Context, trace.Span) {
	if c.tracer == nil {
		return ctx, trace.SpanFromContext(ctx)
	}
	return c.tracer.Start(ctx, name,
		trace.WithAttributes(attrs...),
		trace.WithSpanKind(trace.SpanKindClient),
	)
}

// spanFail records err on span, sets Error status, and returns the err as-is
// so callers can write `return spanFail(...)`. Single helper kills the 3-line
// record+status+return pattern that would otherwise repeat ~20 times below.
func spanFail(span trace.Span, err error, reason string) error {
	span.RecordError(err)
	span.SetStatus(codes.Error, reason)
	return err
}

// sendJSON marshals body (if non-nil), sends the request, reads the full
// response body, and returns status + body. Callers interpret status codes
// (e.g. 404 on heartbeat is ErrGatewayNotFound, not a generic failure).
func (c *cpClient) sendJSON(ctx context.Context, method, path string, body any) (int, []byte, error) {
	var reader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return 0, nil, fmt.Errorf("marshal: %w", err)
		}
		reader = bytes.NewReader(data)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, reader)
	if err != nil {
		return 0, nil, fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("X-Gateway-Key", c.apiKey)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return 0, nil, fmt.Errorf("http: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()
	respBody, _ := io.ReadAll(resp.Body)
	return resp.StatusCode, respBody, nil
}

// --- CP endpoints ---

// Register POSTs the registration payload. Returns the CP-assigned gateway ID.
func (c *cpClient) Register(ctx context.Context, payload RegistrationPayload) (RegistrationResponse, error) {
	ctx, span := c.startSpan(ctx, "stoa-connect.register",
		attribute.String("stoa.instance_name", payload.Hostname),
		attribute.String("stoa.environment", payload.Environment),
	)
	defer span.End()

	status, body, err := c.sendJSON(ctx, http.MethodPost, "/v1/internal/gateways/register", payload)
	if err != nil {
		return RegistrationResponse{}, spanFail(span, fmt.Errorf("register request: %w", err), "register request failed")
	}
	span.SetAttributes(attribute.Int("http.status_code", status))

	if status != http.StatusCreated && status != http.StatusOK {
		return RegistrationResponse{}, spanFail(span, fmt.Errorf("register failed (%d): %s", status, string(body)), "registration rejected")
	}

	var result RegistrationResponse
	if err := json.Unmarshal(body, &result); err != nil {
		return RegistrationResponse{}, spanFail(span, fmt.Errorf("decode registration response: %w", err), "decode failed")
	}

	span.SetAttributes(attribute.String("stoa.gateway_id", result.ID))
	span.SetStatus(codes.Ok, "registered")
	return result, nil
}

// Heartbeat POSTs a heartbeat. Returns ErrGatewayNotFound on 404 (CP purged).
func (c *cpClient) Heartbeat(ctx context.Context, gatewayID string, payload HeartbeatPayload) error {
	ctx, span := c.startSpan(ctx, "stoa-connect.heartbeat",
		attribute.String("stoa.gateway_id", gatewayID),
		attribute.Int("stoa.uptime_seconds", payload.UptimeSeconds),
		attribute.Int("stoa.routes_count", payload.RoutesCount),
		attribute.Int("stoa.discovered_apis", payload.DiscoveredAPIs),
	)
	defer span.End()

	status, body, err := c.sendJSON(ctx, http.MethodPost,
		fmt.Sprintf("/v1/internal/gateways/%s/heartbeat", gatewayID), payload)
	if err != nil {
		return spanFail(span, fmt.Errorf("heartbeat request: %w", err), "heartbeat request failed")
	}
	span.SetAttributes(attribute.Int("http.status_code", status))

	if status == http.StatusNotFound {
		return spanFail(span, ErrGatewayNotFound, "gateway purged from CP")
	}
	if status != http.StatusNoContent && status != http.StatusOK {
		return spanFail(span, fmt.Errorf("heartbeat failed (%d): %s", status, string(body)), "heartbeat rejected")
	}

	span.SetStatus(codes.Ok, "heartbeat sent")
	return nil
}

// ReportDiscovery POSTs discovered APIs.
func (c *cpClient) ReportDiscovery(ctx context.Context, gatewayID string, payload DiscoveryPayload) error {
	ctx, span := c.startSpan(ctx, "stoa-connect.discovery",
		attribute.String("stoa.gateway_id", gatewayID),
		attribute.Int("stoa.discovered_apis", len(payload.APIs)),
	)
	defer span.End()

	status, body, err := c.sendJSON(ctx, http.MethodPost,
		fmt.Sprintf("/v1/internal/gateways/%s/discovery", gatewayID), payload)
	if err != nil {
		return spanFail(span, fmt.Errorf("discovery report request: %w", err), "discovery request failed")
	}
	span.SetAttributes(attribute.Int("http.status_code", status))

	if status != http.StatusOK && status != http.StatusNoContent {
		return spanFail(span, fmt.Errorf("discovery report failed (%d): %s", status, string(body)), "discovery rejected")
	}

	span.SetStatus(codes.Ok, "discovery reported")
	return nil
}

// FetchConfig GETs the gateway config (policies, deployments).
func (c *cpClient) FetchConfig(ctx context.Context, gatewayID string) (*GatewayConfigResponse, error) {
	ctx, span := c.startSpan(ctx, "stoa-connect.sync.fetch-config",
		attribute.String("stoa.gateway_id", gatewayID),
	)
	defer span.End()

	status, body, err := c.sendJSON(ctx, http.MethodGet,
		fmt.Sprintf("/v1/internal/gateways/%s/config", gatewayID), nil)
	if err != nil {
		return nil, spanFail(span, fmt.Errorf("config request: %w", err), "config request failed")
	}
	span.SetAttributes(attribute.Int("http.status_code", status))

	if status != http.StatusOK {
		return nil, spanFail(span, fmt.Errorf("config request failed (%d): %s", status, string(body)), "fetch config rejected")
	}

	var cfg GatewayConfigResponse
	if err := json.Unmarshal(body, &cfg); err != nil {
		return nil, spanFail(span, fmt.Errorf("decode config response: %w", err), "decode failed")
	}
	span.SetAttributes(attribute.Int("stoa.pending_policies", len(cfg.PendingPolicies)))
	span.SetStatus(codes.Ok, "config fetched")
	return &cfg, nil
}

// FetchRoutes GETs the route table filtered by gatewayName (empty = all).
// Unlike the other methods, this endpoint is filtered by gateway_name query
// param rather than a path-scoped gatewayID — it's called before Register
// in some startup paths.
func (c *cpClient) FetchRoutes(ctx context.Context, gatewayName string) ([]adapters.Route, error) {
	ctx, span := c.startSpan(ctx, "stoa-connect.routes.fetch",
		attribute.String("stoa.gateway_name", gatewayName),
	)
	defer span.End()

	path := "/v1/internal/gateways/routes"
	if gatewayName != "" {
		path += "?gateway_name=" + gatewayName
	}
	status, body, err := c.sendJSON(ctx, http.MethodGet, path, nil)
	if err != nil {
		return nil, spanFail(span, fmt.Errorf("routes request: %w", err), "routes request failed")
	}
	span.SetAttributes(attribute.Int("http.status_code", status))

	if status != http.StatusOK {
		return nil, spanFail(span, fmt.Errorf("routes request failed (%d): %s", status, string(body)), "fetch routes rejected")
	}

	var routes []adapters.Route
	if err := json.Unmarshal(body, &routes); err != nil {
		return nil, spanFail(span, fmt.Errorf("decode routes response: %w", err), "decode failed")
	}
	span.SetAttributes(attribute.Int("stoa.routes_count", len(routes)))
	span.SetStatus(codes.Ok, "routes fetched")
	return routes, nil
}

// ReportSyncAck POSTs policy sync results.
func (c *cpClient) ReportSyncAck(ctx context.Context, gatewayID string, payload SyncAckPayload) error {
	var applied, removed, failed int
	for _, r := range payload.SyncedPolicies {
		switch r.Status {
		case "applied":
			applied++
		case "removed":
			removed++
		case "failed":
			failed++
		}
	}
	ctx, span := c.startSpan(ctx, "stoa-connect.sync.ack",
		attribute.String("stoa.gateway_id", gatewayID),
		attribute.Int("stoa.synced_policies", len(payload.SyncedPolicies)),
		attribute.Int("stoa.policies_applied", applied),
		attribute.Int("stoa.policies_removed", removed),
		attribute.Int("stoa.policies_failed", failed),
	)
	defer span.End()

	status, body, err := c.sendJSON(ctx, http.MethodPost,
		fmt.Sprintf("/v1/internal/gateways/%s/sync-ack", gatewayID), payload)
	if err != nil {
		return spanFail(span, fmt.Errorf("sync-ack request: %w", err), "sync-ack request failed")
	}
	span.SetAttributes(attribute.Int("http.status_code", status))

	if status != http.StatusOK && status != http.StatusNoContent {
		return spanFail(span, fmt.Errorf("sync-ack failed (%d): %s", status, string(body)), "sync-ack rejected")
	}
	span.SetStatus(codes.Ok, "sync-ack sent")
	return nil
}

// ReportRouteSyncAck POSTs route sync results.
func (c *cpClient) ReportRouteSyncAck(ctx context.Context, gatewayID string, payload RouteSyncAckPayload) error {
	ctx, span := c.startSpan(ctx, "stoa-connect.routes.ack",
		attribute.String("stoa.gateway_id", gatewayID),
		attribute.Int("stoa.synced_routes", len(payload.SyncedRoutes)),
	)
	defer span.End()

	status, body, err := c.sendJSON(ctx, http.MethodPost,
		fmt.Sprintf("/v1/internal/gateways/%s/route-sync-ack", gatewayID), payload)
	if err != nil {
		return spanFail(span, fmt.Errorf("route-sync-ack request: %w", err), "route-sync-ack request failed")
	}
	span.SetAttributes(attribute.Int("http.status_code", status))

	if status != http.StatusOK && status != http.StatusNoContent {
		return spanFail(span, fmt.Errorf("route-sync-ack failed (%d): %s", status, string(body)), "route-sync-ack rejected")
	}
	span.SetStatus(codes.Ok, "route-sync-ack sent")
	return nil
}
