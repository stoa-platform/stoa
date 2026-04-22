package connect

import (
	"context"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/stoa-platform/stoa-go/internal/connect/adapters"
)

// DiscoveryConfig holds configuration for the discovery loop.
type DiscoveryConfig struct {
	// GatewayAdminURL is the local gateway's admin API URL.
	GatewayAdminURL string
	// GatewayType is the gateway type (kong, gravitee, webmethods, auto).
	GatewayType string
	// Interval between discovery runs.
	Interval time.Duration
	// Adapter-level auth config.
	AdapterConfig adapters.AdapterConfig
}

// DiscoveryConfigFromEnv creates a DiscoveryConfig from environment variables.
func DiscoveryConfigFromEnv() DiscoveryConfig {
	cfg := DiscoveryConfig{
		GatewayAdminURL: os.Getenv("STOA_GATEWAY_ADMIN_URL"),
		GatewayType:     os.Getenv("STOA_GATEWAY_TYPE"),
		Interval:        60 * time.Second,
		AdapterConfig: adapters.AdapterConfig{
			Token:    os.Getenv("STOA_GATEWAY_ADMIN_TOKEN"),
			Username: os.Getenv("STOA_GATEWAY_ADMIN_USER"),
			Password: os.Getenv("STOA_GATEWAY_ADMIN_PASSWORD"),
		},
	}
	if cfg.GatewayType == "" {
		cfg.GatewayType = "auto"
	}
	if interval := os.Getenv("STOA_DISCOVERY_INTERVAL"); interval != "" {
		if d, err := time.ParseDuration(interval); err == nil {
			cfg.Interval = d
		}
	}
	return cfg
}

// ResolveAdapter returns the appropriate adapter for the configured gateway type.
// If type is "auto", it probes each adapter's Detect method.
func ResolveAdapter(ctx context.Context, cfg DiscoveryConfig) (adapters.GatewayAdapter, string, error) {
	acfg := cfg.AdapterConfig

	switch strings.ToLower(cfg.GatewayType) {
	case "kong":
		return adapters.NewKongAdapter(acfg), "kong", nil
	case "gravitee":
		return adapters.NewGraviteeAdapter(acfg), "gravitee", nil
	case "webmethods":
		return adapters.NewWebMethodsAdapter(acfg), "webmethods", nil
	case "auto", "":
		return autoDetect(ctx, cfg.GatewayAdminURL, acfg)
	default:
		return nil, "", fmt.Errorf("unsupported gateway type: %s", cfg.GatewayType)
	}
}

// autoDetect tries each adapter's Detect method against the admin URL.
func autoDetect(ctx context.Context, adminURL string, acfg adapters.AdapterConfig) (adapters.GatewayAdapter, string, error) {
	detectors := []struct {
		name    string
		adapter adapters.GatewayAdapter
	}{
		{"kong", adapters.NewKongAdapter(acfg)},
		{"gravitee", adapters.NewGraviteeAdapter(acfg)},
		{"webmethods", adapters.NewWebMethodsAdapter(acfg)},
	}

	for _, d := range detectors {
		ok, err := d.adapter.Detect(ctx, adminURL)
		if err != nil {
			log.Printf("auto-detect %s error: %v", d.name, err)
			continue
		}
		if ok {
			log.Printf("auto-detected gateway type: %s", d.name)
			return d.adapter, d.name, nil
		}
	}

	return nil, "", fmt.Errorf("could not auto-detect gateway type at %s", adminURL)
}

// StartDiscovery starts a background goroutine that periodically discovers
// APIs from the local gateway and reports them to the Control Plane. See
// runDiscoveryLoop in loop_discovery.go for the loop body.
func (a *Agent) StartDiscovery(ctx context.Context, dcfg DiscoveryConfig) {
	if dcfg.GatewayAdminURL == "" {
		log.Println("discovery skipped: STOA_GATEWAY_ADMIN_URL not set")
		return
	}
	adapter, gwType, err := ResolveAdapter(ctx, dcfg)
	if err != nil {
		log.Printf("discovery setup failed: %v", err)
		return
	}
	log.Printf("discovery started: type=%s url=%s interval=%s", gwType, dcfg.GatewayAdminURL, dcfg.Interval)
	go runDiscoveryLoop(ctx, a, adapter, dcfg.GatewayAdminURL, dcfg.Interval)
}

// runDiscovery performs a single discovery cycle.
func (a *Agent) runDiscovery(ctx context.Context, adapter adapters.GatewayAdapter, adminURL string) {
	start := time.Now()
	apis, err := adapter.Discover(ctx, adminURL)
	ObserveAdminAPICall(start)
	DiscoveryCycles.Inc()

	if err != nil {
		log.Printf("discovery error: %v", err)
		GatewayUp.Set(0)
		return
	}

	GatewayUp.Set(1)
	APIsTotal.Set(float64(len(apis)))
	log.Printf("discovered %d APIs from gateway", len(apis))

	// Convert to payload type for storage and reporting
	payloads := make([]DiscoveredAPIPayload, len(apis))
	for i, api := range apis {
		payloads[i] = DiscoveredAPIPayload{
			Name:       api.Name,
			Version:    api.Version,
			BackendURL: api.BackendURL,
			Paths:      api.Paths,
			Methods:    api.Methods,
			Policies:   api.Policies,
			IsActive:   api.IsActive,
		}
	}
	a.state.SetDiscoveredAPIs(payloads)

	// Report to CP if registered
	if a.state.GatewayID() != "" {
		if err := a.ReportDiscovery(ctx, payloads); err != nil {
			log.Printf("discovery report error: %v", err)
		}
	}
}
