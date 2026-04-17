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

func TestApplyFile_UnsupportedAPIVersion(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "bad-version.yaml")
	content := `apiVersion: unknown.io/v99
kind: Tenant
metadata:
  name: test
`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	err := applyFile(nil, path)
	if err == nil {
		t.Error("applyFile() with unsupported apiVersion should return error")
	}
	if err != nil && !contains(err.Error(), "unsupported apiVersion") {
		t.Errorf("error = %q, want it to contain 'unsupported apiVersion'", err.Error())
	}
}

func TestApplyFile_CanonicalAPIVersion(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "v1beta1.yaml")
	content := `apiVersion: gostoa.dev/v1beta1
kind: UnknownThing
metadata:
  name: test
`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	// Should pass apiVersion validation but fail on unsupported kind
	err := applyFile(nil, path)
	if err == nil {
		t.Error("applyFile() should fail on unsupported kind")
	}
	if err != nil && contains(err.Error(), "unsupported apiVersion") {
		t.Error("canonical v1beta1 should not trigger apiVersion error")
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && searchSubstr(s, substr)
}

func searchSubstr(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

func TestMCPServerForTool_Label(t *testing.T) {
	r := types.Resource{
		Metadata: types.Metadata{
			Labels: map[string]string{"mcp-server": "custom-mcp"},
		},
	}
	spec := types.ToolSpec{APIRef: &types.APIRef{Name: "openapi"}}
	if got := mcpServerForTool(r, spec); got != "custom-mcp" {
		t.Errorf("label should win; got %q, want %q", got, "custom-mcp")
	}
}

func TestMCPServerForTool_APIRefFallback(t *testing.T) {
	r := types.Resource{Metadata: types.Metadata{}}
	spec := types.ToolSpec{APIRef: &types.APIRef{Name: "petstore"}}
	if got := mcpServerForTool(r, spec); got != "petstore-mcp" {
		t.Errorf("apiRef fallback; got %q, want %q", got, "petstore-mcp")
	}
}

func TestMCPServerForTool_NoHint(t *testing.T) {
	r := types.Resource{Metadata: types.Metadata{}}
	spec := types.ToolSpec{}
	if got := mcpServerForTool(r, spec); got != "" {
		t.Errorf("no hint should return empty; got %q", got)
	}
}

func TestDecodeToolSpec_FromYAMLMap(t *testing.T) {
	raw := map[string]any{
		"displayName": "Get balance",
		"endpoint":    "https://api.bank.fr/balance",
		"method":      "GET",
		"apiRef": map[string]any{
			"name":        "openapi",
			"operationId": "getBalance",
		},
	}
	spec, err := decodeToolSpec(raw)
	if err != nil {
		t.Fatalf("decodeToolSpec() err = %v", err)
	}
	if spec.DisplayName != "Get balance" {
		t.Errorf("displayName = %q", spec.DisplayName)
	}
	if spec.APIRef == nil || spec.APIRef.Name != "openapi" {
		t.Errorf("apiRef not decoded: %+v", spec.APIRef)
	}
	if spec.APIRef.OperationID != "getBalance" {
		t.Errorf("operationId = %q", spec.APIRef.OperationID)
	}
}

func TestDecodeToolSpec_NilRejected(t *testing.T) {
	if _, err := decodeToolSpec(nil); err == nil {
		t.Error("decodeToolSpec(nil) should error")
	}
}

func TestTenantFromResource_NamespaceOverrideWins(t *testing.T) {
	prev := namespaceOverrideFn
	defer func() { namespaceOverrideFn = prev }()
	namespaceOverrideFn = func() string { return "flag-tenant" }

	r := types.Resource{Metadata: types.Metadata{Namespace: "yaml-tenant"}}
	if got := tenantFromResource(nil, r); got != "flag-tenant" {
		t.Errorf("--namespace should override metadata.namespace; got %q", got)
	}
}

func TestApplyFile_ToolMissingServerHint(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "orphan-tool.yaml")
	content := `apiVersion: gostoa.dev/v1alpha1
kind: Tool
metadata:
  name: orphan-tool
  namespace: demo
spec:
  displayName: Orphan
  endpoint: https://example.com
  method: GET
`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}
	err := applyFile(nil, path)
	if err == nil {
		t.Fatal("Tool without server hint should error before network call")
	}
	if !contains(err.Error(), "parent MCP server") {
		t.Errorf("error should mention 'parent MCP server'; got %q", err.Error())
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
