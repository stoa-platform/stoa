// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package apply

import (
	"fmt"
	"io"
	"net/http"
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

Supported kinds: API, Tenant, Gateway, Subscription, Consumer, Contract,
MCPServer, ServiceAccount, Plan, Webhook.

Examples:
  # Apply an API definition
  stoactl apply -f api.yaml

  # Apply a consumer
  stoactl apply -f consumer.yaml

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

	// Validate apiVersion — accept legacy versions with a deprecation warning
	if !types.IsAcceptedAPIVersion(resource.APIVersion) {
		return fmt.Errorf("unsupported apiVersion %q in %s (expected %s)", resource.APIVersion, path, types.CanonicalAPIVersion)
	}
	if resource.APIVersion != types.CanonicalAPIVersion {
		output.Warn("apiVersion %q is deprecated, use %q instead", resource.APIVersion, types.CanonicalAPIVersion)
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
	case "Tenant":
		if err := applyGeneric(c, "/v1/tenants", resource); err != nil {
			return fmt.Errorf("failed to apply %s/%s: %w", resource.Kind, resource.Metadata.Name, err)
		}
	case "Gateway":
		if err := applyGeneric(c, "/v1/admin/gateways", resource); err != nil {
			return fmt.Errorf("failed to apply %s/%s: %w", resource.Kind, resource.Metadata.Name, err)
		}
	case "Subscription":
		if err := applyGeneric(c, "/v1/subscriptions", resource); err != nil {
			return fmt.Errorf("failed to apply %s/%s: %w", resource.Kind, resource.Metadata.Name, err)
		}
	case "Consumer":
		tenant := tenantFromResource(c, resource)
		if err := applyGeneric(c, fmt.Sprintf("/v1/consumers/%s", tenant), resource); err != nil {
			return fmt.Errorf("failed to apply %s/%s: %w", resource.Kind, resource.Metadata.Name, err)
		}
	case "Contract":
		tenant := tenantFromResource(c, resource)
		if err := applyGeneric(c, fmt.Sprintf("/v1/tenants/%s/contracts", tenant), resource); err != nil {
			return fmt.Errorf("failed to apply %s/%s: %w", resource.Kind, resource.Metadata.Name, err)
		}
	case "MCPServer":
		spec, _ := resource.Spec.(map[string]any)
		displayName, _ := spec["displayName"].(string)
		description, _ := spec["description"].(string)
		if _, err := c.CreateMCPServer(resource.Metadata.Name, displayName, description); err != nil {
			return fmt.Errorf("failed to apply %s/%s: %w", resource.Kind, resource.Metadata.Name, err)
		}
	case "ServiceAccount":
		if err := applyGeneric(c, "/v1/service-accounts", resource); err != nil {
			return fmt.Errorf("failed to apply %s/%s: %w", resource.Kind, resource.Metadata.Name, err)
		}
	case "Plan":
		tenant := tenantFromResource(c, resource)
		if err := applyGeneric(c, fmt.Sprintf("/v1/plans/%s", tenant), resource); err != nil {
			return fmt.Errorf("failed to apply %s/%s: %w", resource.Kind, resource.Metadata.Name, err)
		}
	case "Webhook":
		tenant := tenantFromResource(c, resource)
		if err := applyGeneric(c, fmt.Sprintf("/v1/tenants/%s/webhooks", tenant), resource); err != nil {
			return fmt.Errorf("failed to apply %s/%s: %w", resource.Kind, resource.Metadata.Name, err)
		}
	default:
		return fmt.Errorf("unsupported resource kind: %s", resource.Kind)
	}

	output.Success("%s/%s configured", resource.Kind, resource.Metadata.Name)
	return nil
}

// applyGeneric sends a POST to the given path with the resource spec merged with metadata.
// The API endpoint is expected to handle create-or-update semantics.
func applyGeneric(c *client.Client, path string, resource types.Resource) error {
	body := buildApplyBody(resource)

	resp, err := c.Do("POST", path, body)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode >= http.StatusOK && resp.StatusCode < http.StatusMultipleChoices {
		return nil
	}

	respBody, _ := io.ReadAll(resp.Body)
	return fmt.Errorf("API error (%d): %s", resp.StatusCode, string(respBody))
}

// buildApplyBody merges resource metadata.name into the spec map for the API payload.
func buildApplyBody(resource types.Resource) map[string]any {
	body := make(map[string]any)
	body["name"] = resource.Metadata.Name

	if specMap, ok := resource.Spec.(map[string]any); ok {
		for k, v := range specMap {
			body[k] = v
		}
	}

	if len(resource.Metadata.Labels) > 0 {
		body["labels"] = resource.Metadata.Labels
	}

	return body
}

// tenantFromResource returns the tenant from metadata.namespace or falls back to the client's configured tenant.
func tenantFromResource(c *client.Client, resource types.Resource) string {
	if resource.Metadata.Namespace != "" {
		return resource.Metadata.Namespace
	}
	return c.TenantID()
}
