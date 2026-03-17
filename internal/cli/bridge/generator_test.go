// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package bridge

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stoa-platform/stoa-go/pkg/types"
)

func TestGenerateToolFiles_CreatesFiles(t *testing.T) {
	dir := t.TempDir()

	enabled := true
	tools := []types.Resource{
		{
			APIVersion: types.ToolCRDAPIVersion,
			Kind:       types.ToolCRDKind,
			Metadata: types.Metadata{
				Name:      "list-pets",
				Namespace: "tenant-acme",
				Labels:    map[string]string{"generated-by": "stoactl-bridge"},
			},
			Spec: types.ToolSpec{
				DisplayName: "List all pets",
				Description: "List all pets",
				Endpoint:    "https://api.example.com/v1/pets",
				Method:      "GET",
				Timeout:     "30s",
				Enabled:     &enabled,
			},
		},
		{
			APIVersion: types.ToolCRDAPIVersion,
			Kind:       types.ToolCRDKind,
			Metadata: types.Metadata{
				Name:      "create-pet",
				Namespace: "tenant-acme",
			},
			Spec: types.ToolSpec{
				DisplayName: "Create a pet",
				Description: "Create a pet",
				Endpoint:    "https://api.example.com/v1/pets",
				Method:      "POST",
				Timeout:     "30s",
				Enabled:     &enabled,
			},
		},
	}

	result, err := GenerateToolFiles(tools, GenerateOptions{OutputDir: dir})
	if err != nil {
		t.Fatalf("GenerateToolFiles error: %v", err)
	}

	if len(result.Files) != 2 {
		t.Fatalf("expected 2 files, got %d", len(result.Files))
	}

	// Verify first file
	data, err := os.ReadFile(filepath.Join(dir, "list-pets.yaml"))
	if err != nil {
		t.Fatalf("read list-pets.yaml: %v", err)
	}
	content := string(data)
	if !strings.Contains(content, "apiVersion: gostoa.dev/v1alpha1") {
		t.Error("missing apiVersion in output")
	}
	if !strings.Contains(content, "kind: Tool") {
		t.Error("missing kind in output")
	}
	if !strings.Contains(content, "name: list-pets") {
		t.Error("missing name in output")
	}
	if !strings.Contains(content, "namespace: tenant-acme") {
		t.Error("missing namespace in output")
	}
	if !strings.Contains(content, "displayName: List all pets") {
		t.Error("missing displayName in output")
	}
	if !strings.Contains(content, "method: GET") {
		t.Error("missing method in output")
	}

	// Verify second file exists
	if _, err := os.Stat(filepath.Join(dir, "create-pet.yaml")); os.IsNotExist(err) {
		t.Error("create-pet.yaml not created")
	}
}

func TestGenerateToolFiles_CreatesOutputDir(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "nested", "output")

	tools := []types.Resource{
		{
			APIVersion: types.ToolCRDAPIVersion,
			Kind:       types.ToolCRDKind,
			Metadata:   types.Metadata{Name: "test-tool"},
			Spec:       types.ToolSpec{DisplayName: "Test"},
		},
	}

	result, err := GenerateToolFiles(tools, GenerateOptions{OutputDir: dir})
	if err != nil {
		t.Fatalf("GenerateToolFiles error: %v", err)
	}
	if len(result.Files) != 1 {
		t.Errorf("expected 1 file, got %d", len(result.Files))
	}
}

func TestMarshalTool_ValidYAML(t *testing.T) {
	enabled := true
	tool := types.Resource{
		APIVersion: types.ToolCRDAPIVersion,
		Kind:       types.ToolCRDKind,
		Metadata: types.Metadata{
			Name:      "get-pet-by-id",
			Namespace: "tenant-acme",
			Labels:    map[string]string{"generated-by": "stoactl-bridge", "source-spec": "petstore"},
		},
		Spec: types.ToolSpec{
			DisplayName: "Get a pet by ID",
			Description: "Get a pet by ID",
			Endpoint:    "https://api.example.com/v1/pets/{petId}",
			Method:      "GET",
			Timeout:     "30s",
			Enabled:     &enabled,
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"petId": map[string]any{
						"type": "string",
					},
				},
				"required": []any{"petId"},
			},
			Authentication: &types.AuthConfig{
				Type: "bearer",
				SecretRef: &types.SecretRef{
					Name: "my-secret",
					Key:  "token",
				},
			},
			Tags: []string{"pets"},
			APIRef: &types.APIRef{
				Name:        "petstore",
				Version:     "1.0.0",
				OperationID: "getPetById",
			},
		},
	}

	data, err := MarshalTool(tool)
	if err != nil {
		t.Fatalf("MarshalTool error: %v", err)
	}

	content := string(data)

	// Verify key fields are present in YAML
	checks := []string{
		"apiVersion: gostoa.dev/v1alpha1",
		"kind: Tool",
		"name: get-pet-by-id",
		"namespace: tenant-acme",
		"generated-by: stoactl-bridge",
		"source-spec: petstore",
		"displayName: Get a pet by ID",
		"endpoint: https://api.example.com/v1/pets/{petId}",
		"method: GET",
		"timeout: 30s",
		"enabled: true",
		"type: bearer",
		"name: my-secret",
		"key: token",
	}

	for _, check := range checks {
		if !strings.Contains(content, check) {
			t.Errorf("YAML output missing %q\n\nFull output:\n%s", check, content)
		}
	}
}
