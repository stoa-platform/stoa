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
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
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
	Endpoint     string  // OTLP gRPC endpoint (e.g., "localhost:4317")
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

	// OTLP gRPC exporter
	exporter, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithEndpoint(cfg.Endpoint),
		otlptracegrpc.WithInsecure(), // VPS/K8s internal network
	)
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
