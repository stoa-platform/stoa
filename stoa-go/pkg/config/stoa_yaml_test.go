// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadStoaYaml_FullSpec(t *testing.T) {
	content := `
name: petstore
version: 1.2.0
tags: [payments, internal]
endpoints:
  - path: /pets
    method: GET
    description: List all pets
  - path: /pets/{id}
    method: GET
rate_limit:
  requests_per_minute: 100
  burst: 20
auth:
  type: jwt
  issuer: https://auth.example.com
  required: true
`
	spec := mustLoad(t, content)

	if spec.Name != "petstore" {
		t.Errorf("name: got %q want petstore", spec.Name)
	}
	if spec.Version != "1.2.0" {
		t.Errorf("version: got %q want 1.2.0", spec.Version)
	}
	if len(spec.Endpoints) != 2 {
		t.Errorf("endpoints count: got %d want 2", len(spec.Endpoints))
	}
	if spec.RateLimit == nil || spec.RateLimit.RequestsPerMinute != 100 {
		t.Error("rate_limit.requests_per_minute not parsed correctly")
	}
	if spec.Auth == nil || spec.Auth.Type != "jwt" {
		t.Error("auth.type not parsed correctly")
	}
	if len(spec.Tags) != 2 {
		t.Errorf("tags count: got %d want 2", len(spec.Tags))
	}
}

func TestLoadStoaYaml_MinimalSpec(t *testing.T) {
	spec := mustLoad(t, "name: my-api\n")

	if spec.Name != "my-api" {
		t.Errorf("name: got %q want my-api", spec.Name)
	}
	if spec.Version != "1.0.0" {
		t.Errorf("default version: got %q want 1.0.0", spec.Version)
	}
	if len(spec.Endpoints) != 0 {
		t.Errorf("expected no endpoints, got %d", len(spec.Endpoints))
	}
}

func TestLoadStoaYaml_EndpointDefaultMethod(t *testing.T) {
	content := "name: api\nendpoints:\n  - path: /items\n"
	spec := mustLoad(t, content)

	if spec.Endpoints[0].Method != "GET" {
		t.Errorf("default method: got %q want GET", spec.Endpoints[0].Method)
	}
}

func TestLoadStoaYaml_MissingName(t *testing.T) {
	mustFail(t, "version: 1.0.0\n", "should error when name is missing")
}

func TestLoadStoaYaml_InvalidVersion(t *testing.T) {
	mustFail(t, "name: foo\nversion: not-a-version\n", "should error for non-semver version")
}

func TestLoadStoaYaml_InvalidAuthType(t *testing.T) {
	mustFail(t, "name: foo\nauth:\n  type: basic\n", "should error for unknown auth type")
}

func TestLoadStoaYaml_RateLimitZero(t *testing.T) {
	mustFail(t, "name: foo\nrate_limit:\n  requests_per_minute: 0\n", "should error for requests_per_minute=0")
}

func TestLoadStoaYaml_EndpointMissingPath(t *testing.T) {
	mustFail(t, "name: foo\nendpoints:\n  - method: GET\n", "should error for endpoint without path")
}

func TestLoadStoaYaml_FileNotFound(t *testing.T) {
	_, err := LoadStoaYaml("/nonexistent/stoa.yaml")
	if err == nil {
		t.Fatal("expected error for nonexistent file")
	}
}

func TestLoadStoaYaml_InvalidYAML(t *testing.T) {
	mustFail(t, "not: [valid: yaml", "should error for malformed YAML")
}

func TestValidate_AllAuthTypes(t *testing.T) {
	for _, authType := range []string{"jwt", "api_key", "mtls", "oauth2", "none"} {
		content := "name: foo\nauth:\n  type: " + authType + "\n"
		mustLoad(t, content)
	}
}

// --- helpers ---

func mustLoad(t *testing.T, content string) *StoaYamlSpec {
	t.Helper()
	path := writeTemp(t, content)
	spec, err := LoadStoaYaml(path)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	return spec
}

func mustFail(t *testing.T, content, reason string) {
	t.Helper()
	path := writeTemp(t, content)
	_, err := LoadStoaYaml(path)
	if err == nil {
		t.Fatalf("expected error: %s", reason)
	}
}

func writeTemp(t *testing.T, content string) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "stoa.yaml")
	if err := os.WriteFile(path, []byte(content), 0600); err != nil {
		t.Fatal(err)
	}
	return path
}
