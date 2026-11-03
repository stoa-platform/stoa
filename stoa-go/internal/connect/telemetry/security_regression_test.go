package telemetry

import (
	"bytes"
	"context"
	"os"
	"os/exec"
	"strings"
	"testing"

	"github.com/go-logr/logr/funcr"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func TestRegressionCAB2353OTLPEndpointIsNotLogged(t *testing.T) {
	// Isolate the process-global OTel logger from the rest of the test suite.
	const childKey = "STOA_OTEL_LOG_REGRESSION_CHILD"
	if os.Getenv(childKey) != "1" {
		cmd := exec.Command(os.Args[0], "-test.run=^TestRegressionCAB2353OTLPEndpointIsNotLogged$")
		cmd.Env = append(os.Environ(), childKey+"=1")
		if output, err := cmd.CombinedOutput(); err != nil {
			t.Fatalf("OTel logging regression: %v\n%s", err, output)
		}
		return
	}

	const host = "otel-regression.invalid:4318"
	for _, tc := range []struct {
		name     string
		exporter *otlptrace.Exporter
	}{
		{"http", otlptracehttp.NewUnstarted(otlptracehttp.WithEndpointURL("https://" + host))},
		{"grpc", otlptracegrpc.NewUnstarted(otlptracegrpc.WithEndpoint(host), otlptracegrpc.WithInsecure())},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var logs bytes.Buffer
			otel.SetLogger(funcr.New(func(_, message string) {
				logs.WriteString(message)
			}, funcr.Options{Verbosity: 4}))

			// No spans or started exporter: provider creation never sends traffic.
			provider := sdktrace.NewTracerProvider(sdktrace.WithSyncer(tc.exporter))
			t.Cleanup(func() {
				if err := provider.Shutdown(context.Background()); err != nil {
					t.Errorf("shut down tracer provider: %v", err)
				}
			})

			if !strings.Contains(logs.String(), "TracerProvider created") {
				t.Fatal("expected verbose provider diagnostic to be captured")
			}
			if strings.Contains(logs.String(), host) {
				t.Fatal("provider diagnostic disclosed the OTLP endpoint (GHSA-8wmf-6v46-5gfg)")
			}
		})
	}
}
