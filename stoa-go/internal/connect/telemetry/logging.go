package telemetry

import (
	"context"
	"encoding/json"
	"io"
	"log"
	"os"
	"strings"
	"sync"
	"time"

	"go.opentelemetry.io/otel/trace"
)

type LogConfig struct {
	ServiceName  string
	Version      string
	InstanceName string
	Environment  string
	TenantID     string
	Writer       io.Writer
	Now          func() time.Time
}

type StructuredLogger struct {
	cfg LogConfig
	mu  sync.Mutex
}

func LogConfigFromEnv(version, instanceName, environment string) LogConfig {
	return LogConfig{
		ServiceName:  "stoa-connect",
		Version:      version,
		InstanceName: instanceName,
		Environment:  environment,
		TenantID:     os.Getenv("STOA_TENANT_ID"),
	}
}

func NewStructuredLogger(cfg LogConfig) *StructuredLogger {
	if cfg.ServiceName == "" {
		cfg.ServiceName = "stoa-connect"
	}
	if cfg.Writer == nil {
		cfg.Writer = os.Stdout
	}
	if cfg.Now == nil {
		cfg.Now = time.Now
	}
	return &StructuredLogger{cfg: cfg}
}

func ConfigureStructuredLogging(cfg LogConfig) *StructuredLogger {
	logger := NewStructuredLogger(cfg)
	log.SetFlags(0)
	log.SetPrefix("")
	log.SetOutput(logger)
	return logger
}

func (l *StructuredLogger) Write(p []byte) (int, error) {
	for _, line := range strings.Split(strings.TrimRight(string(p), "\n"), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		if err := l.emit(context.Background(), inferLevel(line), line, nil); err != nil {
			return 0, err
		}
	}
	return len(p), nil
}

func (l *StructuredLogger) Info(ctx context.Context, message string, fields ...any) {
	_ = l.emit(ctx, "info", message, fields)
}

func (l *StructuredLogger) emit(ctx context.Context, level, message string, fields []any) error {
	entry := map[string]any{
		"timestamp":           l.cfg.Now().UTC().Format(time.RFC3339Nano),
		"level":               level,
		"message":             message,
		"service.name":        l.cfg.ServiceName,
		"service.version":     l.cfg.Version,
		"service.instance.id": l.cfg.InstanceName,
		"environment":         l.cfg.Environment,
		"tenant_id":           l.cfg.TenantID,
		"trace_id":            "-",
		"span_id":             "-",
	}
	if spanCtx := trace.SpanContextFromContext(ctx); spanCtx.IsValid() {
		entry["trace_id"] = spanCtx.TraceID().String()
		entry["span_id"] = spanCtx.SpanID().String()
	}
	for i := 0; i+1 < len(fields); i += 2 {
		if key, ok := fields[i].(string); ok && key != "" {
			entry[key] = fields[i+1]
		}
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	return json.NewEncoder(l.cfg.Writer).Encode(entry)
}

func inferLevel(message string) string {
	lower := strings.ToLower(message)
	switch {
	case strings.HasPrefix(lower, "warning"):
		return "warn"
	case strings.Contains(lower, "error"), strings.Contains(lower, "failed"), strings.HasPrefix(lower, "listen:"), strings.HasPrefix(lower, "shutdown:"):
		return "error"
	default:
		return "info"
	}
}
