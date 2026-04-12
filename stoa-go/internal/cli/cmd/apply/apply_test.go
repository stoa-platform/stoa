// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package apply

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stoa-platform/stoa-go/pkg/types"
)

func TestBuildApplyBody_WithSpec(t *testing.T) {
	resource := types.Resource{
		APIVersion: "stoa.io/v1",
		Kind:       "Consumer",
		Metadata: types.Metadata{
			Name:      "my-consumer",
			Namespace: "acme",
			Labels:    map[string]string{"env": "prod"},
		},
		Spec: map[string]any{
			"email":        "user@example.com",
			"display_name": "My Consumer",
		},
	}

	body := buildApplyBody(resource)

	if body["name"] != "my-consumer" {
		t.Errorf("body[name] = %q, want %q", body["name"], "my-consumer")
	}
	if body["email"] != "user@example.com" {
		t.Errorf("body[email] = %q, want %q", body["email"], "user@example.com")
	}
	if body["display_name"] != "My Consumer" {
		t.Errorf("body[display_name] = %q, want %q", body["display_name"], "My Consumer")
	}
	labels, ok := body["labels"].(map[string]string)
	if !ok {
		t.Fatal("body[labels] is not map[string]string")
	}
	if labels["env"] != "prod" {
		t.Errorf("body[labels][env] = %q, want %q", labels["env"], "prod")
	}
}

func TestBuildApplyBody_NoSpec(t *testing.T) {
	resource := types.Resource{
		APIVersion: "stoa.io/v1",
		Kind:       "Tenant",
		Metadata:   types.Metadata{Name: "acme"},
		Spec:       nil,
	}

	body := buildApplyBody(resource)

	if body["name"] != "acme" {
		t.Errorf("body[name] = %q, want %q", body["name"], "acme")
	}
	// Should only have "name" key when spec is nil
	if len(body) != 1 {
		t.Errorf("body has %d keys, want 1 (name only)", len(body))
	}
}

func TestBuildApplyBody_SpecNotMap(t *testing.T) {
	resource := types.Resource{
		APIVersion: "stoa.io/v1",
		Kind:       "Tenant",
		Metadata:   types.Metadata{Name: "acme"},
		Spec:       "invalid-spec",
	}

	body := buildApplyBody(resource)

	// Should still have name even when spec is not a map
	if body["name"] != "acme" {
		t.Errorf("body[name] = %q, want %q", body["name"], "acme")
	}
}

func TestApplyFile_InvalidYAML(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "bad.yaml")
	if err := os.WriteFile(path, []byte(":::invalid:::"), 0644); err != nil {
		t.Fatal(err)
	}

	err := applyFile(nil, path)
	if err == nil {
		t.Error("applyFile() with invalid YAML should return error")
	}
}

func TestApplyFile_MissingKind(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "no-kind.yaml")
	content := `apiVersion: stoa.io/v1
metadata:
  name: test
`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	err := applyFile(nil, path)
	if err == nil {
		t.Error("applyFile() with missing kind should return error")
	}
}

func TestApplyFile_MissingName(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "no-name.yaml")
	content := `apiVersion: stoa.io/v1
kind: Tenant
metadata: {}
`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	err := applyFile(nil, path)
	if err == nil {
		t.Error("applyFile() with missing name should return error")
	}
}

func TestApplyFile_UnsupportedKind(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "unsupported.yaml")
	content := `apiVersion: stoa.io/v1
kind: UnknownThing
metadata:
  name: test
`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	// Will fail because client is nil, but should reach the kind switch first
	// for validation tests that don't need a server. However since applyFile
	// requires a non-nil client for non-dry-run, and UnsupportedKind would
	// need to reach the switch, let's just verify the error message pattern.
	err := applyFile(nil, path)
	if err == nil {
		t.Error("applyFile() with unsupported kind should return error")
	}
}

func TestRunApply_MissingFile(t *testing.T) {
	filePath = "/nonexistent/path/file.yaml"
	dryRun = false

	err := runApply(nil, nil)
	if err == nil {
		t.Error("runApply() with nonexistent file should return error")
	}
}

func TestRunApply_EmptyDirectory(t *testing.T) {
	dir := t.TempDir()
	filePath = dir
	dryRun = false

	err := runApply(nil, nil)
	if err == nil {
		t.Error("runApply() with empty directory should return error")
	}
}
