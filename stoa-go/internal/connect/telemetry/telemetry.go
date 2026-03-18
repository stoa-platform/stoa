// Package telemetry provides OpenTelemetry initialization for stoa-connect.
//
// Graceful degradation: if OTEL_EXPORTER_OTLP_ENDPOINT is not set,
// a no-op tracer is used (zero overhead). This allows the same binary
// to run with or without a collector.
package telemetry

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.27.0"
	"go.opentelemetry.io/otel/trace"
	"go.opentelemetry.io/otel/trace/noop"
)

// Config holds OTel configuration for stoa-connect.
type Config struct {
	ServiceName  string
	Version      string
	InstanceName string
	Environment  string
	Endpoint     string  // OTLP endpoint: gRPC ("localhost:4317") or HTTP ("https://otlp.example.com")
	SampleRate   float64 // 0.0 to 1.0, default 1.0
}

// ConfigFromEnv creates a telemetry Config from environment variables.
func ConfigFromEnv(version, instanceName, environment string) Config {
	cfg := Config{
		ServiceName:  "stoa-connect",
		Version:      version,
		InstanceName: instanceName,
		Environment:  environment,
		Endpoint:     os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
		SampleRate:   1.0,
	}
	if rate := os.Getenv("OTEL_SAMPLE_RATE"); rate != "" {
		if r, err := strconv.ParseFloat(rate, 64); err == nil && r >= 0 && r <= 1 {
			cfg.SampleRate = r
		}
	}
	return cfg
}

// Shutdown is a function that flushes and shuts down the tracer provider.
type Shutdown func(ctx context.Context) error

// Init initializes OpenTelemetry tracing. If no endpoint is configured,
// it returns a no-op tracer with a no-op shutdown function (zero overhead).
func Init(ctx context.Context, cfg Config) (trace.Tracer, Shutdown, error) {
	// No endpoint → no-op tracer (graceful degradation)
	if cfg.Endpoint == "" {
		noopProvider := noop.NewTracerProvider()
		otel.SetTracerProvider(noopProvider)
		otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
			propagation.TraceContext{},
			propagation.Baggage{},
		))
		tracer := noopProvider.Tracer(cfg.ServiceName)
		return tracer, func(context.Context) error { return nil }, nil
	}

	// Build resource attributes using explicit attributes only
	// (avoids schema URL conflicts between resource.Default and semconv versions)
	res := resource.NewWithAttributes(
		semconv.SchemaURL,
		semconv.ServiceName(cfg.ServiceName),
		semconv.ServiceVersion(cfg.Version),
		semconv.DeploymentEnvironmentName(cfg.Environment),
		semconv.ServiceInstanceID(cfg.InstanceName),
	)

	// Create exporter: HTTP if endpoint starts with http(s)://, gRPC otherwise
	exporter, err := newExporter(ctx, cfg.Endpoint)
	if err != nil {
		return nil, nil, fmt.Errorf("create OTLP exporter: %w", err)
	}

	// Sampler: ParentBased(TraceIdRatioBased) — respects parent decision
	sampler := sdktrace.ParentBased(
		sdktrace.TraceIDRatioBased(cfg.SampleRate),
	)

	// Trace provider with batch span processor
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter,
			sdktrace.WithBatchTimeout(5*time.Second),
		),
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sampler),
	)

	// Set global provider and W3C propagator
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	tracer := tp.Tracer(cfg.ServiceName)
	shutdown := func(ctx context.Context) error {
		return tp.Shutdown(ctx)
	}

	return tracer, shutdown, nil
}

// isHTTPEndpoint returns true if the endpoint looks like an HTTP(S) URL.
func isHTTPEndpoint(endpoint string) bool {
	return strings.HasPrefix(endpoint, "http://") || strings.HasPrefix(endpoint, "https://")
}

// newExporter creates the appropriate OTLP exporter based on the endpoint format.
// HTTP endpoints (http:// or https://) use OTLP/HTTP — needed for VPS agents
// going through nginx ingress. Plain host:port uses OTLP/gRPC — used inside K8s.
// Basic auth for HTTP is handled via OTEL_EXPORTER_OTLP_HEADERS env var
// (e.g., "Authorization=Basic dXNlcjpwYXNz").
func newExporter(ctx context.Context, endpoint string) (*otlptrace.Exporter, error) {
	if isHTTPEndpoint(endpoint) {
		opts := []otlptracehttp.Option{
			otlptracehttp.WithEndpointURL(endpoint),
		}
		return otlptracehttp.New(ctx, opts...)
	}
	// Default: gRPC (K8s internal, insecure)
	return otlptracegrpc.New(ctx,
		otlptracegrpc.WithEndpoint(endpoint),
		otlptracegrpc.WithInsecure(),
	)
}
