// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package bridge

import (
	"fmt"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"

	bridgelib "github.com/stoa-platform/stoa-go/internal/cli/bridge"
	"github.com/stoa-platform/stoa-go/pkg/client"
	"github.com/stoa-platform/stoa-go/pkg/output"
	"github.com/stoa-platform/stoa-go/pkg/types"
)

var (
	namespace   string
	outputDir   string
	apply       bool
	serverName  string
	server      string
	authSecret  string
	includeTags []string
	excludeTags []string
	includeOps  []string
	timeout     string
	dryRun      bool
)

// NewBridgeCmd creates the bridge command
func NewBridgeCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "bridge <spec-file>",
		Short: "Generate Tool CRDs from an OpenAPI spec",
		Long: `Bridge converts OpenAPI 3.x operations into STOA Tool CRD resources.

Each operation becomes a Tool CRD YAML file, ready for 'stoactl apply -f'.
This enables any REST API to be exposed as MCP tools through the STOA Gateway.

Examples:
  # Generate Tool CRDs from a Petstore spec
  stoactl bridge petstore.yaml --namespace tenant-acme

  # Preview without writing files
  stoactl bridge petstore.yaml --namespace tenant-acme --dry-run

  # Filter by tags
  stoactl bridge petstore.yaml --namespace tenant-acme --include-tags payments

  # Override server URL
  stoactl bridge petstore.yaml --namespace tenant-acme --server https://api.internal.com

  # Apply directly to gateway
  stoactl bridge petstore.yaml --namespace tenant-acme --apply`,
		Args: cobra.ExactArgs(1),
		RunE: runBridge,
	}

	cmd.Flags().StringVarP(&namespace, "namespace", "n", "", "Target namespace for generated tools (required)")
	cmd.Flags().StringVarP(&outputDir, "output", "o", "./tools/", "Output directory for generated YAML files")
	cmd.Flags().BoolVar(&apply, "apply", false, "Apply tools directly to gateway via API")
	cmd.Flags().StringVar(&serverName, "server-name", "", "MCP server name for --apply (default: derived from spec title)")
	cmd.Flags().StringVar(&server, "server", "", "Override servers[0].url from spec")
	cmd.Flags().StringVar(&authSecret, "auth-secret", "", "Secret name for authentication (generates secretRef)")
	cmd.Flags().StringSliceVar(&includeTags, "include-tags", nil, "Only include operations with these tags")
	cmd.Flags().StringSliceVar(&excludeTags, "exclude-tags", nil, "Exclude operations with these tags")
	cmd.Flags().StringSliceVar(&includeOps, "include-ops", nil, "Only include these operationIds")
	cmd.Flags().StringVar(&timeout, "timeout", "30s", "Default timeout for generated tools")
	cmd.Flags().BoolVar(&dryRun, "dry-run", false, "Parse and map, show summary, don't write files")

	if err := cmd.MarkFlagRequired("namespace"); err != nil {
		panic(err)
	}

	return cmd
}

func runBridge(cmd *cobra.Command, args []string) error {
	specFile := args[0]

	// Step 1: Parse the OpenAPI spec
	parsed, err := bridgelib.ParseOpenAPIFile(specFile)
	if err != nil {
		return fmt.Errorf("failed to parse spec: %w", err)
	}

	output.Success("✓ Parsed OpenAPI spec: %s v%s", parsed.Title, parsed.Version)

	// Derive source-spec label from filename
	sourceSpec := strings.TrimSuffix(filepath.Base(specFile), filepath.Ext(specFile))

	// Step 2: Map operations to Tool CRDs
	opts := bridgelib.MapOptions{
		Namespace:   namespace,
		BaseURL:     server,
		AuthSecret:  authSecret,
		Timeout:     timeout,
		SourceSpec:  sourceSpec,
		IncludeTags: includeTags,
		ExcludeTags: excludeTags,
		IncludeOps:  includeOps,
	}

	result := bridgelib.MapOperationsToTools(parsed.Doc, opts)

	if len(result.Tools) == 0 {
		output.Info("No operations matched the filters. Nothing to generate.")
		return nil
	}

	output.Success("✓ Mapped %d operations to Tool CRDs", len(result.Tools))

	// Print warnings
	for _, w := range result.Warnings {
		output.Info("  ⚠ %s", w)
	}

	// Dry-run: show summary and exit
	if dryRun {
		output.Info("")
		output.Info("Tools (dry-run):")
		for _, tool := range result.Tools {
			spec := tool.Spec.(types.ToolSpec)
			output.Info("  - %s (%s %s)", tool.Metadata.Name, spec.Method, spec.Endpoint)
		}
		return nil
	}

	// --apply mode: create MCP server + register tools via CP API
	if apply {
		c, err := client.New()
		if err != nil {
			return fmt.Errorf("failed to create API client: %w", err)
		}

		if !c.IsAuthenticated() {
			return fmt.Errorf("not authenticated — run 'stoactl auth login' first")
		}

		// Derive server name from spec title if not provided
		name := serverName
		if name == "" {
			name = sourceSpec + "-mcp"
		}

		serverID, err := c.CreateMCPServer(name, name, "Auto-bridged from "+filepath.Base(specFile))
		if err != nil {
			return fmt.Errorf("failed to create MCP server: %w", err)
		}

		output.Success("Created MCP server %q (id=%s)", name, serverID)

		for _, tool := range result.Tools {
			spec := tool.Spec.(types.ToolSpec)
			if err := c.AddToolToServer(serverID, tool.Metadata.Name, spec); err != nil {
				output.Error("Failed to register tool %q: %v", tool.Metadata.Name, err)
				continue
			}
			output.Info("  + %s", tool.Metadata.Name)
		}

		output.Success("Registered %d tools on MCP server %q", len(result.Tools), name)
		return nil
	}

	// Step 3: Generate YAML files
	genResult, err := bridgelib.GenerateToolFiles(result.Tools, bridgelib.GenerateOptions{
		OutputDir: outputDir,
	})
	if err != nil {
		return fmt.Errorf("failed to generate files: %w", err)
	}

	output.Success("✓ Generated %d Tool CRDs → %s", len(genResult.Files), outputDir)
	for _, f := range genResult.Files {
		output.Info("  - %s", filepath.Base(f))
	}

	for _, w := range genResult.Warnings {
		output.Info("  ⚠ %s", w)
	}

	return nil
}
