package connect

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

// rawEvent is an un-interpreted SSE event pulled off the wire.
// Dispatch to business handlers (sync-deployment, heartbeat, ...) happens
// in the caller — sseStream only parses the wire format.
type rawEvent struct {
	Type string
	Data []byte
}

// Default scanner buffer caps used by sseStream. Exposed as package-level
// constants so tests can reason about the max-message threshold.
const (
	// sseScannerInitialBuf is the initial token buffer size; matches the
	// bufio default so small events are zero-realloc.
	sseScannerInitialBuf = 64 << 10 // 64 KB
	// sseScannerMaxBuf is the hard cap for a single SSE event payload.
	// Chosen to accommodate large OpenAPI specs inlined in desired_state.
	// Default bufio.MaxScanTokenSize (64 KB) was insufficient — see
	// REWRITE-BUGS.md F.6.
	sseScannerMaxBuf = 1 << 20 // 1 MB
)

// sseStream is the Control Plane SSE transport.
//
// Pure transport: it connects to /v1/internal/gateways/{id}/events, parses
// the wire format, and pipes rawEvents into a caller-supplied sink until the
// stream ends. No dependencies on adapters, sync, or Agent state — the outer
// loop (StartDeploymentStream / loops.runSSEStream in S9) owns reconnect,
// dispatch, and business logic.
//
// Unlike cpClient's http.Client which has a 15s timeout, the SSE client has
// NO timeout — the stream stays open indefinitely under normal operation.
// Both clients share the same otelhttp-wrapped RoundTripper for consistent
// W3C traceparent propagation.
type sseStream struct {
	client  *http.Client
	tracer  trace.Tracer // may be nil before SetTracer
	baseURL string
	apiKey  string
}

// newSSEStream wires the shared transport into a no-timeout http.Client for
// the long-lived SSE connection.
func newSSEStream(baseURL, apiKey string, transport http.RoundTripper) *sseStream {
	return &sseStream{
		client:  &http.Client{Transport: transport},
		baseURL: baseURL,
		apiKey:  apiKey,
	}
}

// SetTracer installs the OpenTelemetry tracer used for the stream span.
func (s *sseStream) SetTracer(t trace.Tracer) {
	s.tracer = t
}

func (s *sseStream) startSpan(ctx context.Context, name string, attrs ...attribute.KeyValue) (context.Context, trace.Span) {
	if s.tracer == nil {
		return ctx, trace.SpanFromContext(ctx)
	}
	return s.tracer.Start(ctx, name,
		trace.WithAttributes(attrs...),
		trace.WithSpanKind(trace.SpanKindClient),
	)
}

// Run connects to the gateway's SSE events endpoint and invokes sink for
// each rawEvent parsed off the wire. It returns the terminal cause: an HTTP
// error, an unexpected status, a scanner error (including bufio.ErrTooLong
// if a single event payload exceeds sseScannerMaxBuf), a sink error, or
// io.EOF if the server closed the stream cleanly.
//
// The context passed to sink is derived from the stream span, so handler
// spans nest correctly under "stoa-connect.sse.stream".
//
// Run is a blocking, single-connection call. Callers implement reconnect
// outside (see runSSEStream in S9).
func (s *sseStream) Run(ctx context.Context, gatewayID string, sink func(context.Context, rawEvent) error) error {
	ctx, span := s.startSpan(ctx, "stoa-connect.sse.stream",
		attribute.String("stoa.gateway_id", gatewayID),
	)
	defer span.End()

	url := fmt.Sprintf("%s/v1/internal/gateways/%s/events", s.baseURL, gatewayID)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return spanFail(span, fmt.Errorf("create SSE request: %w", err), "create request failed")
	}
	req.Header.Set("X-Gateway-Key", s.apiKey)
	req.Header.Set("Accept", "text/event-stream")
	req.Header.Set("Cache-Control", "no-cache")

	resp, err := s.client.Do(req)
	if err != nil {
		return spanFail(span, fmt.Errorf("SSE connect: %w", err), "SSE connect failed")
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		return spanFail(span, fmt.Errorf("SSE endpoint returned %d", resp.StatusCode), "SSE rejected")
	}
	log.Printf("sse-stream: connected to %s", url)
	span.SetStatus(codes.Ok, "connected")

	scanner := bufio.NewScanner(resp.Body)
	// Default token buffer is bufio.MaxScanTokenSize (64 KB). Events carrying
	// large desired_state JSON (OpenAPI spec inlined) would hit bufio.ErrTooLong
	// and the loop would exit silently without propagating the reason. We
	// allocate the same 64 KB initial but raise max to 1 MB and rely on
	// scanner.Err() below to surface ErrTooLong if ever hit.
	scanner.Buffer(make([]byte, 0, sseScannerInitialBuf), sseScannerMaxBuf)

	var eventType string
	var dataLines []string
	for scanner.Scan() {
		line := scanner.Text()

		if line == "" {
			// Empty line terminates an event.
			if eventType != "" && len(dataLines) > 0 {
				data := strings.Join(dataLines, "\n")
				if err := sink(ctx, rawEvent{Type: eventType, Data: []byte(data)}); err != nil {
					return spanFail(span, fmt.Errorf("sink: %w", err), "sink returned error")
				}
			}
			eventType = ""
			dataLines = nil
			continue
		}

		switch {
		case strings.HasPrefix(line, "event:"):
			eventType = strings.TrimSpace(strings.TrimPrefix(line, "event:"))
		case strings.HasPrefix(line, "data:"):
			dataLines = append(dataLines, strings.TrimSpace(strings.TrimPrefix(line, "data:")))
		}
		// Ignore "id:", "retry:", and comment lines starting with ":".
	}

	if err := scanner.Err(); err != nil {
		return spanFail(span, fmt.Errorf("SSE read: %w", err), "scanner error")
	}

	// Scanner exited without error → server closed the stream cleanly.
	// Caller treats io.EOF as a signal to reconnect via backoff policy.
	return io.EOF
}
