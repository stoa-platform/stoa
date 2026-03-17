// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package doctor

import (
	"context"
	"fmt"
	"time"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/pkg/output"
)

// Check represents a diagnostic check
type Check interface {
	Name() string
	Run(ctx context.Context) CheckResult
}

// CheckResult holds the outcome of a diagnostic check
type CheckResult struct {
	Pass    bool
	Message string
}

// NewDoctorCmd creates the doctor command
func NewDoctorCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "doctor",
		Short: "Check system health and prerequisites",
		Long: `Run diagnostic checks to verify your STOA development environment.

Checks:
  - Docker is running
  - Gateway is healthy
  - OS Keychain is accessible
  - API key is valid
  - Gateway port is available
  - MCP endpoint responds

Examples:
  stoactl doctor`,
		Args: cobra.NoArgs,
		RunE: runDoctor,
	}
}

func runDoctor(cmd *cobra.Command, args []string) error {
	checks := []Check{
		&DockerRunningCheck{},
		&GatewayHealthCheck{URL: "http://localhost:8080/health"},
		&KeychainAccessCheck{},
		&APIKeyValidCheck{},
		&PortAvailableCheck{Port: 8080},
		&MCPEndpointCheck{URL: "http://localhost:8080/mcp/sse"},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	fmt.Println("STOA Doctor")
	fmt.Println()

	allPass := true
	for _, check := range checks {
		result := check.Run(ctx)
		if result.Pass {
			fmt.Printf("  ✓ %s: %s\n", check.Name(), result.Message)
		} else {
			fmt.Printf("  ✗ %s: %s\n", check.Name(), result.Message)
			allPass = false
		}
	}

	fmt.Println()
	if allPass {
		output.Success("All checks passed.")
	} else {
		output.Info("Some checks failed. Fix the issues above and re-run 'stoactl doctor'.")
	}

	return nil
}
