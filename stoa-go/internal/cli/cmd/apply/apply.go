// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package apply

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"

	"github.com/stoa-platform/stoa-go/pkg/client"
	"github.com/stoa-platform/stoa-go/pkg/output"
	"github.com/stoa-platform/stoa-go/pkg/types"
)

var (
	filePath string
	dryRun   bool
)

// NewApplyCmd creates the apply command
func NewApplyCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "apply",
		Short: "Apply a configuration to a resource by file",
		Long: `Apply a configuration to a resource by file.

The resource will be created if it doesn't exist, or updated if it does.
This command is idempotent and safe to run multiple times.

Examples:
  # Apply an API definition
  stoactl apply -f api.yaml

  # Apply multiple resources from a directory
  stoactl apply -f ./manifests/

  # Dry-run to validate without applying
  stoactl apply -f api.yaml --dry-run`,
		RunE: runApply,
	}

	cmd.Flags().StringVarP(&filePath, "file", "f", "", "Path to YAML file or directory (required)")
	cmd.Flags().BoolVar(&dryRun, "dry-run", false, "Validate without applying changes")

	_ = cmd.MarkFlagRequired("file")

	return cmd
}

func runApply(cmd *cobra.Command, args []string) error {
	c, err := client.New()
	if err != nil {
		return err
	}

	// Check if path is directory
	info, err := os.Stat(filePath)
	if err != nil {
		return fmt.Errorf("failed to access %s: %w", filePath, err)
	}

	var files []string
	if info.IsDir() {
		// Find all YAML files in directory
		entries, err := os.ReadDir(filePath)
		if err != nil {
			return fmt.Errorf("failed to read directory: %w", err)
		}
		for _, entry := range entries {
			if !entry.IsDir() && (filepath.Ext(entry.Name()) == ".yaml" || filepath.Ext(entry.Name()) == ".yml") {
				files = append(files, filepath.Join(filePath, entry.Name()))
			}
		}
		if len(files) == 0 {
			return fmt.Errorf("no YAML files found in %s", filePath)
		}
	} else {
		files = []string{filePath}
	}

	// Process each file
	for _, file := range files {
		if err := applyFile(c, file); err != nil {
			return err
		}
	}

	return nil
}

func applyFile(c *client.Client, path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("failed to read %s: %w", path, err)
	}

	var resource types.Resource
	if err := yaml.Unmarshal(data, &resource); err != nil {
		return fmt.Errorf("failed to parse %s: %w", path, err)
	}

	// Validate resource
	if resource.APIVersion == "" || resource.Kind == "" {
		return fmt.Errorf("invalid resource in %s: missing apiVersion or kind", path)
	}

	if resource.Metadata.Name == "" {
		return fmt.Errorf("invalid resource in %s: missing metadata.name", path)
	}

	// Dry run
	if dryRun {
		if err := c.ValidateResource(&resource); err != nil {
			output.Error("Validation failed for %s: %v", path, err)
			return err
		}
		output.Info("%s/%s validated (dry run)", resource.Kind, resource.Metadata.Name)
		return nil
	}

	// Apply resource based on kind
	switch resource.Kind {
	case "API":
		if err := c.CreateOrUpdateAPI(&resource); err != nil {
			return fmt.Errorf("failed to apply %s/%s: %w", resource.Kind, resource.Metadata.Name, err)
		}
	default:
		return fmt.Errorf("unsupported resource kind: %s", resource.Kind)
	}

	output.Success("%s/%s configured", resource.Kind, resource.Metadata.Name)
	return nil
}
