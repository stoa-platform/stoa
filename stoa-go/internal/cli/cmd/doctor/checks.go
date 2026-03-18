// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package doctor

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"os/exec"
	"strings"
	"time"

	"github.com/stoa-platform/stoa-go/pkg/config"
	"github.com/stoa-platform/stoa-go/pkg/keyring"
)

// DockerRunningCheck verifies Docker is running
type DockerRunningCheck struct{}

func (c *DockerRunningCheck) Name() string { return "Docker" }

func (c *DockerRunningCheck) Run(ctx context.Context) CheckResult {
	cmd := exec.CommandContext(ctx, "docker", "info", "--format", "{{.ServerVersion}}")
	out, err := cmd.Output()
	if err != nil {
		return CheckResult{Pass: false, Message: "not running (install: https://docs.docker.com/get-docker/)"}
	}
	version := strings.TrimSpace(string(out))
	return CheckResult{Pass: true, Message: fmt.Sprintf("running (v%s)", version)}
}

// GatewayHealthCheck verifies the gateway health endpoint
type GatewayHealthCheck struct {
	URL string
}

func (c *GatewayHealthCheck) Name() string { return "Gateway" }

func (c *GatewayHealthCheck) Run(ctx context.Context) CheckResult {
	client := &http.Client{Timeout: 5 * time.Second}
	req, err := http.NewRequestWithContext(ctx, "GET", c.URL, nil)
	if err != nil {
		return CheckResult{Pass: false, Message: fmt.Sprintf("invalid URL: %v", err)}
	}

	resp, err := client.Do(req)
	if err != nil {
		return CheckResult{Pass: false, Message: fmt.Sprintf("not responding (%s)", c.URL)}
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK {
		return CheckResult{Pass: true, Message: fmt.Sprintf("healthy (%s)", c.URL)}
	}
	return CheckResult{Pass: false, Message: fmt.Sprintf("unhealthy (status %d)", resp.StatusCode)}
}

// KeychainAccessCheck verifies OS Keychain is accessible
type KeychainAccessCheck struct{}

func (c *KeychainAccessCheck) Name() string { return "Keychain" }

func (c *KeychainAccessCheck) Run(ctx context.Context) CheckResult {
	store := keyring.NewOSKeyring()
	if store.Available() {
		return CheckResult{Pass: true, Message: fmt.Sprintf("accessible (%s)", store.Name())}
	}
	return CheckResult{Pass: false, Message: "not accessible (keychain may be locked)"}
}

// APIKeyValidCheck verifies a valid API key exists
type APIKeyValidCheck struct{}

func (c *APIKeyValidCheck) Name() string { return "API key" }

func (c *APIKeyValidCheck) Run(ctx context.Context) CheckResult {
	cfg, err := config.Load()
	if err != nil {
		return CheckResult{Pass: false, Message: "config not found"}
	}

	ctxCfg, err := cfg.GetCurrentContext()
	if err != nil {
		return CheckResult{Pass: false, Message: "no context set"}
	}

	store := keyring.NewOSKeyring()
	tokenData, err := store.Get(ctxCfg.Name)
	if err != nil || tokenData == nil {
		// Fallback to file
		tokenCache, err := config.LoadTokenCache()
		if err != nil || tokenCache == nil || tokenCache.AccessToken == "" {
			return CheckResult{Pass: false, Message: "not found (run 'stoactl auth login')"}
		}
		if time.Now().Unix() > tokenCache.ExpiresAt {
			return CheckResult{Pass: false, Message: "expired (run 'stoactl auth login')"}
		}
		remaining := time.Until(time.Unix(tokenCache.ExpiresAt, 0))
		return CheckResult{Pass: true, Message: fmt.Sprintf("valid (expires in %s, stored in file)", remaining.Round(time.Minute))}
	}

	if time.Now().Unix() > tokenData.ExpiresAt {
		return CheckResult{Pass: false, Message: "expired (run 'stoactl auth login')"}
	}

	remaining := time.Until(time.Unix(tokenData.ExpiresAt, 0))
	return CheckResult{Pass: true, Message: fmt.Sprintf("valid (expires in %s)", remaining.Round(time.Minute))}
}

// PortAvailableCheck verifies a port is available for binding
type PortAvailableCheck struct {
	Port int
}

func (c *PortAvailableCheck) Name() string { return fmt.Sprintf("Port %d", c.Port) }

func (c *PortAvailableCheck) Run(ctx context.Context) CheckResult {
	ln, err := net.Listen("tcp", fmt.Sprintf(":%d", c.Port))
	if err != nil {
		return CheckResult{Pass: false, Message: fmt.Sprintf("in use (port %d)", c.Port)}
	}
	ln.Close()
	return CheckResult{Pass: true, Message: "available"}
}

// MCPEndpointCheck verifies the MCP SSE endpoint responds
type MCPEndpointCheck struct {
	URL string
}

func (c *MCPEndpointCheck) Name() string { return "MCP endpoint" }

func (c *MCPEndpointCheck) Run(ctx context.Context) CheckResult {
	client := &http.Client{Timeout: 5 * time.Second}
	req, err := http.NewRequestWithContext(ctx, "GET", c.URL, nil)
	if err != nil {
		return CheckResult{Pass: false, Message: fmt.Sprintf("invalid URL: %v", err)}
	}

	resp, err := client.Do(req)
	if err != nil {
		return CheckResult{Pass: false, Message: "not responding"}
	}
	defer resp.Body.Close()

	// MCP SSE may return 200 with text/event-stream, or other success codes
	if resp.StatusCode >= 200 && resp.StatusCode < 400 {
		return CheckResult{Pass: true, Message: fmt.Sprintf("responding (%s)", c.URL)}
	}
	return CheckResult{Pass: false, Message: fmt.Sprintf("error (status %d)", resp.StatusCode)}
}
