package telemetry

import (
	"context"
	"testing"
)

func TestConfigFromEnv(t *testing.T) {
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
	t.Setenv("OTEL_SAMPLE_RATE", "0.5")

	cfg := ConfigFromEnv("1.0.0", "kong-01", "staging")

	if cfg.ServiceName != "stoa-connect" {
		t.Errorf("expected service name stoa-connect, got %s", cfg.ServiceName)
	}
	if cfg.Version != "1.0.0" {
		t.Errorf("expected version 1.0.0, got %s", cfg.Version)
	}
	if cfg.InstanceName != "kong-01" {
		t.Errorf("expected instance name kong-01, got %s", cfg.InstanceName)
	}
	if cfg.Environment != "staging" {
		t.Errorf("expected environment staging, got %s", cfg.Environment)
	}
	if cfg.Endpoint != "localhost:4317" {
		t.Errorf("expected endpoint localhost:4317, got %s", cfg.Endpoint)
	}
	if cfg.SampleRate != 0.5 {
		t.Errorf("expected sample rate 0.5, got %f", cfg.SampleRate)
	}
}

func TestConfigFromEnvDefaults(t *testing.T) {
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
	t.Setenv("OTEL_SAMPLE_RATE", "")

	cfg := ConfigFromEnv("dev", "test-host", "production")

	if cfg.Endpoint != "" {
		t.Errorf("expected empty endpoint, got %s", cfg.Endpoint)
	}
	if cfg.SampleRate != 1.0 {
		t.Errorf("expected default sample rate 1.0, got %f", cfg.SampleRate)
	}
}

func TestConfigFromEnvInvalidSampleRate(t *testing.T) {
	t.Setenv("OTEL_SAMPLE_RATE", "not-a-number")

	cfg := ConfigFromEnv("dev", "test", "prod")

	if cfg.SampleRate != 1.0 {
		t.Errorf("expected default 1.0 on invalid input, got %f", cfg.SampleRate)
	}
}

func TestConfigFromEnvSampleRateOutOfRange(t *testing.T) {
	t.Setenv("OTEL_SAMPLE_RATE", "2.0")

	cfg := ConfigFromEnv("dev", "test", "prod")

	if cfg.SampleRate != 1.0 {
		t.Errorf("expected default 1.0 for out-of-range value, got %f", cfg.SampleRate)
	}
}

func TestInitNoEndpoint(t *testing.T) {
	ctx := context.Background()
	cfg := Config{
		ServiceName:  "stoa-connect",
		Version:      "1.0.0",
		InstanceName: "test",
		Environment:  "test",
		Endpoint:     "", // No endpoint → no-op
		SampleRate:   1.0,
	}

	tracer, shutdown, err := Init(ctx, cfg)
	if err != nil {
		t.Fatalf("Init failed: %v", err)
	}
	if tracer == nil {
		t.Fatal("expected non-nil tracer")
	}
	if shutdown == nil {
		t.Fatal("expected non-nil shutdown")
	}

	// Verify no-op behavior: spans should not be recording
	_, span := tracer.Start(ctx, "test")
	if span.IsRecording() {
		t.Error("expected non-recording span from no-op tracer")
	}
	if span.SpanContext().IsValid() {
		t.Error("expected invalid span context from no-op tracer")
	}
	span.End()

	// Verify shutdown is safe to call
	if err := shutdown(ctx); err != nil {
		t.Errorf("shutdown returned error: %v", err)
	}
}

func TestInitNoEndpointCreatesSpans(t *testing.T) {
	ctx := context.Background()
	cfg := Config{
		ServiceName: "stoa-connect",
		Endpoint:    "", // No-op
	}

	tracer, shutdown, err := Init(ctx, cfg)
	if err != nil {
		t.Fatalf("Init failed: %v", err)
	}
	defer func() { _ = shutdown(ctx) }()

	// No-op tracer should create spans without error
	_, span := tracer.Start(ctx, "test-span")
	span.End()
}

func TestInitWithEndpoint(t *testing.T) {
	// Use a non-routable endpoint — the SDK creates the exporter eagerly
	// but only connects lazily (on first span export), so Init succeeds.
	ctx := context.Background()
	cfg := Config{
		ServiceName:  "stoa-connect",
		Version:      "1.0.0",
		InstanceName: "test-host",
		Environment:  "test",
		Endpoint:     "localhost:4317",
		SampleRate:   1.0, // Always sample in tests
	}

	tracer, shutdown, err := Init(ctx, cfg)
	if err != nil {
		t.Fatalf("Init failed: %v", err)
	}
	if tracer == nil {
		t.Fatal("expected non-nil tracer")
	}

	// Verify it's a real provider: spans should be recording
	_, span := tracer.Start(ctx, "test-span")
	if !span.IsRecording() {
		t.Error("expected recording span from real tracer")
	}
	if !span.SpanContext().TraceID().IsValid() {
		t.Error("expected valid trace ID from real tracer")
	}
	span.End()

	// Shutdown flushes — may warn about connection failure, but should not error fatally
	if err := shutdown(ctx); err != nil {
		// Connection errors to non-existent collector are expected
		t.Logf("shutdown warning (expected): %v", err)
	}
}
