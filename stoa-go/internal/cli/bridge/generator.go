// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package bridge

import (
	"fmt"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"

	"github.com/stoa-platform/stoa-go/pkg/types"
)

// GenerateOptions configures YAML generation
type GenerateOptions struct {
	OutputDir string
}

// GenerateResult holds the outcome of generation
type GenerateResult struct {
	Files    []string
	Warnings []string
}

// GenerateToolFiles writes each Tool resource as a separate YAML file
func GenerateToolFiles(tools []types.Resource, opts GenerateOptions) (*GenerateResult, error) {
	result := &GenerateResult{}

	if err := os.MkdirAll(opts.OutputDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create output directory: %w", err)
	}

	for _, tool := range tools {
		filename := tool.Metadata.Name + ".yaml"
		path := filepath.Join(opts.OutputDir, filename)

		data, err := yaml.Marshal(tool)
		if err != nil {
			result.Warnings = append(result.Warnings, fmt.Sprintf("failed to marshal %s: %v", tool.Metadata.Name, err))
			continue
		}

		if err := os.WriteFile(path, data, 0644); err != nil {
			return nil, fmt.Errorf("failed to write %s: %w", path, err)
		}

		result.Files = append(result.Files, path)
	}

	return result, nil
}

// MarshalTool returns the YAML representation of a Tool resource
func MarshalTool(tool types.Resource) ([]byte, error) {
	return yaml.Marshal(tool)
}
