package telemetry

import (
	"bytes"
	"context"
	"encoding/json"
	"testing"
	"time"

	"go.opentelemetry.io/otel/trace"
)

func TestRegressionStoaConnectStructuredLoggerWritesContractFields(t *testing.T) {
	var buf bytes.Buffer
	logger := NewStructuredLogger(LogConfig{
		ServiceName:  "stoa-connect",
		Version:      "1.2.3",
		InstanceName: "wm-local",
		Environment:  "dev",
		TenantID:     "tenant-a",
		Writer:       &buf,
		Now:          func() time.Time { return time.Unix(1700000000, 0) },
	})

	traceID, _ := trace.TraceIDFromHex("4bf92f3577b34da6a3ce929d0e0e4736")
	spanID, _ := trace.SpanIDFromHex("00f067aa0ba902b7")
	ctx := trace.ContextWithSpanContext(context.Background(), trace.NewSpanContext(trace.SpanContextConfig{
		TraceID: traceID,
		SpanID:  spanID,
	}))

	logger.Info(ctx, "received telemetry events via webhook", "accepted", 3)
	entry := decodeLogEntry(t, buf.Bytes())

	want := map[string]any{
		"level":               "info",
		"message":             "received telemetry events via webhook",
		"service.name":        "stoa-connect",
		"service.version":     "1.2.3",
		"service.instance.id": "wm-local",
		"environment":         "dev",
		"tenant_id":           "tenant-a",
		"trace_id":            traceID.String(),
		"span_id":             spanID.String(),
		"accepted":            float64(3),
	}
	for key, value := range want {
		if entry[key] != value {
			t.Fatalf("expected %s=%v, got %v", key, value, entry[key])
		}
	}
}

func decodeLogEntry(t *testing.T, data []byte) map[string]any {
	t.Helper()
	var entry map[string]any
	if err := json.Unmarshal(data, &entry); err != nil {
		t.Fatalf("decode log entry: %v; data=%s", err, string(data))
	}
	return entry
}
