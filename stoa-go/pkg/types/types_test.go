// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package types

import (
	"encoding/json"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// TestResourceYAMLMarshalUnmarshal tests YAML serialization
func TestResourceYAMLMarshalUnmarshal(t *testing.T) {
	original := Resource{
		APIVersion: "stoa.io/v1",
		Kind:       "API",
		Metadata: Metadata{
			Name:      "test-api",
			Namespace: "default",
			Labels: map[string]string{
				"env":  "production",
				"team": "platform",
			},
		},
		Spec: map[string]interface{}{
			"version":     "v1",
			"description": "Test API",
		},
	}

	// Marshal to YAML
	data, err := yaml.Marshal(original)
	if err != nil {
		t.Fatalf("yaml.Marshal() error = %v", err)
	}

	// Unmarshal back
	var result Resource
	err = yaml.Unmarshal(data, &result)
	if err != nil {
		t.Fatalf("yaml.Unmarshal() error = %v", err)
	}

	// Verify fields
	if result.APIVersion != original.APIVersion {
		t.Errorf("APIVersion = %q, want %q", result.APIVersion, original.APIVersion)
	}
	if result.Kind != original.Kind {
		t.Errorf("Kind = %q, want %q", result.Kind, original.Kind)
	}
	if result.Metadata.Name != original.Metadata.Name {
		t.Errorf("Metadata.Name = %q, want %q", result.Metadata.Name, original.Metadata.Name)
	}
	if result.Metadata.Namespace != original.Metadata.Namespace {
		t.Errorf("Metadata.Namespace = %q, want %q", result.Metadata.Namespace, original.Metadata.Namespace)
	}
	if result.Metadata.Labels["env"] != "production" {
		t.Errorf("Metadata.Labels[env] = %q, want %q", result.Metadata.Labels["env"], "production")
	}
}

// TestResourceJSONMarshalUnmarshal tests JSON serialization
func TestResourceJSONMarshalUnmarshal(t *testing.T) {
	original := Resource{
		APIVersion: "stoa.io/v1",
		Kind:       "API",
		Metadata: Metadata{
			Name:      "test-api",
			Namespace: "production",
			Labels: map[string]string{
				"version": "v2",
			},
		},
		Spec: map[string]interface{}{
			"upstream": map[string]interface{}{
				"url":     "https://backend.example.com",
				"timeout": "30s",
			},
		},
	}

	// Marshal to JSON
	data, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("json.Marshal() error = %v", err)
	}

	// Unmarshal back
	var result Resource
	err = json.Unmarshal(data, &result)
	if err != nil {
		t.Fatalf("json.Unmarshal() error = %v", err)
	}

	if result.APIVersion != original.APIVersion {
		t.Errorf("APIVersion = %q, want %q", result.APIVersion, original.APIVersion)
	}
	if result.Metadata.Name != original.Metadata.Name {
		t.Errorf("Metadata.Name = %q, want %q", result.Metadata.Name, original.Metadata.Name)
	}
}

// TestAPIJSONMarshalUnmarshal tests API type JSON handling
func TestAPIJSONMarshalUnmarshal(t *testing.T) {
	original := API{
		ID:          "api-123",
		Name:        "payment-api",
		Version:     "v2",
		Description: "Payment processing API",
		Tenant:      "acme-corp",
		Status:      "active",
		Upstream:    "https://payments.internal.acme.com",
		Path:        "/api/payments",
		CreatedAt:   "2024-01-15T10:30:00Z",
		UpdatedAt:   "2024-01-20T14:45:00Z",
	}

	data, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("json.Marshal() error = %v", err)
	}

	var result API
	err = json.Unmarshal(data, &result)
	if err != nil {
		t.Fatalf("json.Unmarshal() error = %v", err)
	}

	if result.ID != original.ID {
		t.Errorf("ID = %q, want %q", result.ID, original.ID)
	}
	if result.Name != original.Name {
		t.Errorf("Name = %q, want %q", result.Name, original.Name)
	}
	if result.Version != original.Version {
		t.Errorf("Version = %q, want %q", result.Version, original.Version)
	}
	if result.Status != original.Status {
		t.Errorf("Status = %q, want %q", result.Status, original.Status)
	}
	if result.Upstream != original.Upstream {
		t.Errorf("Upstream = %q, want %q", result.Upstream, original.Upstream)
	}
	if result.Path != original.Path {
		t.Errorf("Path = %q, want %q", result.Path, original.Path)
	}
}

// TestAPIListResponseJSON tests APIListResponse JSON handling
func TestAPIListResponseJSON(t *testing.T) {
	original := APIListResponse{
		Items: []API{
			{ID: "1", Name: "api-1", Status: "active"},
			{ID: "2", Name: "api-2", Status: "inactive"},
			{ID: "3", Name: "api-3", Status: "pending"},
		},
		TotalCount: 3,
	}

	data, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("json.Marshal() error = %v", err)
	}

	var result APIListResponse
	err = json.Unmarshal(data, &result)
	if err != nil {
		t.Fatalf("json.Unmarshal() error = %v", err)
	}

	if result.TotalCount != original.TotalCount {
		t.Errorf("TotalCount = %d, want %d", result.TotalCount, original.TotalCount)
	}
	if len(result.Items) != len(original.Items) {
		t.Fatalf("Items length = %d, want %d", len(result.Items), len(original.Items))
	}

	for i, item := range result.Items {
		if item.Name != original.Items[i].Name {
			t.Errorf("Items[%d].Name = %q, want %q", i, item.Name, original.Items[i].Name)
		}
	}
}

// TestAPISpecYAML tests APISpec YAML handling
func TestAPISpecYAML(t *testing.T) {
	yamlData := `
version: v1
description: Test API with full spec
upstream:
  url: https://backend.example.com
  timeout: 30s
  retries: 3
routing:
  path: /api/v1
  stripPath: true
  methods:
    - GET
    - POST
authentication:
  required: true
  providers:
    - type: jwt
      header: Authorization
      issuer: https://auth.example.com
policies:
  rateLimit:
    requestsPerHour: 1000
  cors:
    origins:
      - https://example.com
      - https://app.example.com
  cache:
    enabled: true
    ttlSeconds: 300
catalog:
  visibility: public
  categories:
    - payments
    - financial
`

	var spec APISpec
	err := yaml.Unmarshal([]byte(yamlData), &spec)
	if err != nil {
		t.Fatalf("yaml.Unmarshal() error = %v", err)
	}

	// Verify top-level fields
	if spec.Version != "v1" {
		t.Errorf("Version = %q, want %q", spec.Version, "v1")
	}
	if spec.Description != "Test API with full spec" {
		t.Errorf("Description = %q, want %q", spec.Description, "Test API with full spec")
	}

	// Verify upstream
	if spec.Upstream.URL != "https://backend.example.com" {
		t.Errorf("Upstream.URL = %q, want %q", spec.Upstream.URL, "https://backend.example.com")
	}
	if spec.Upstream.Timeout != "30s" {
		t.Errorf("Upstream.Timeout = %q, want %q", spec.Upstream.Timeout, "30s")
	}
	if spec.Upstream.Retries != 3 {
		t.Errorf("Upstream.Retries = %d, want %d", spec.Upstream.Retries, 3)
	}

	// Verify routing
	if spec.Routing.Path != "/api/v1" {
		t.Errorf("Routing.Path = %q, want %q", spec.Routing.Path, "/api/v1")
	}
	if !spec.Routing.StripPath {
		t.Error("Routing.StripPath = false, want true")
	}
	if len(spec.Routing.Methods) != 2 {
		t.Errorf("Routing.Methods length = %d, want 2", len(spec.Routing.Methods))
	}

	// Verify authentication
	if !spec.Authentication.Required {
		t.Error("Authentication.Required = false, want true")
	}
	if len(spec.Authentication.Providers) != 1 {
		t.Fatalf("Authentication.Providers length = %d, want 1", len(spec.Authentication.Providers))
	}
	if spec.Authentication.Providers[0].Type != "jwt" {
		t.Errorf("Providers[0].Type = %q, want %q", spec.Authentication.Providers[0].Type, "jwt")
	}

	// Verify policies
	if spec.Policies.RateLimit == nil {
		t.Fatal("Policies.RateLimit is nil")
	}
	if spec.Policies.RateLimit.RequestsPerHour != 1000 {
		t.Errorf("RateLimit.RequestsPerHour = %d, want 1000", spec.Policies.RateLimit.RequestsPerHour)
	}

	if spec.Policies.CORS == nil {
		t.Fatal("Policies.CORS is nil")
	}
	if len(spec.Policies.CORS.Origins) != 2 {
		t.Errorf("CORS.Origins length = %d, want 2", len(spec.Policies.CORS.Origins))
	}

	if spec.Policies.Cache == nil {
		t.Fatal("Policies.Cache is nil")
	}
	if !spec.Policies.Cache.Enabled {
		t.Error("Cache.Enabled = false, want true")
	}
	if spec.Policies.Cache.TTLSeconds != 300 {
		t.Errorf("Cache.TTLSeconds = %d, want 300", spec.Policies.Cache.TTLSeconds)
	}

	// Verify catalog
	if spec.Catalog.Visibility != "public" {
		t.Errorf("Catalog.Visibility = %q, want %q", spec.Catalog.Visibility, "public")
	}
	if len(spec.Catalog.Categories) != 2 {
		t.Errorf("Catalog.Categories length = %d, want 2", len(spec.Catalog.Categories))
	}
}

// TestMetadataWithOptionalFields tests Metadata with and without optional fields
func TestMetadataWithOptionalFields(t *testing.T) {
	tests := []struct {
		name       string
		yamlData   string
		wantName   string
		wantNs     string
		wantLabels int
	}{
		{
			name:       "full metadata",
			yamlData:   "name: full-api\nnamespace: production\nlabels:\n  env: prod\n  team: platform",
			wantName:   "full-api",
			wantNs:     "production",
			wantLabels: 2,
		},
		{
			name:       "minimal metadata",
			yamlData:   "name: minimal-api",
			wantName:   "minimal-api",
			wantNs:     "",
			wantLabels: 0,
		},
		{
			name:       "with namespace only",
			yamlData:   "name: ns-api\nnamespace: staging",
			wantName:   "ns-api",
			wantNs:     "staging",
			wantLabels: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var m Metadata
			err := yaml.Unmarshal([]byte(tt.yamlData), &m)
			if err != nil {
				t.Fatalf("yaml.Unmarshal() error = %v", err)
			}

			if m.Name != tt.wantName {
				t.Errorf("Name = %q, want %q", m.Name, tt.wantName)
			}
			if m.Namespace != tt.wantNs {
				t.Errorf("Namespace = %q, want %q", m.Namespace, tt.wantNs)
			}
			if len(m.Labels) != tt.wantLabels {
				t.Errorf("Labels length = %d, want %d", len(m.Labels), tt.wantLabels)
			}
		})
	}
}

// TestAPIWithOptionalFields tests API JSON with omitempty behavior
func TestAPIWithOptionalFields(t *testing.T) {
	// Minimal API
	minimal := API{
		ID:   "123",
		Name: "minimal",
	}

	data, err := json.Marshal(minimal)
	if err != nil {
		t.Fatalf("json.Marshal() error = %v", err)
	}

	// Verify required fields are present
	jsonStr := string(data)
	if !strings.Contains(jsonStr, `"id"`) {
		t.Error("JSON should contain 'id' field")
	}
	if !strings.Contains(jsonStr, `"name"`) {
		t.Error("JSON should contain 'name' field")
	}
}

// TestResourceFromRealYAMLExample tests parsing a realistic resource YAML
func TestResourceFromRealYAMLExample(t *testing.T) {
	yamlContent := `
apiVersion: stoa.io/v1
kind: API
metadata:
  name: petstore-api
  namespace: default
  labels:
    app: petstore
    version: v3
spec:
  version: v3.1.0
  description: Petstore API for managing pets
  upstream:
    url: https://petstore.internal.example.com
    timeout: 30s
  routing:
    path: /api/petstore
    stripPath: true
  authentication:
    required: true
`

	var resource Resource
	err := yaml.Unmarshal([]byte(yamlContent), &resource)
	if err != nil {
		t.Fatalf("yaml.Unmarshal() error = %v", err)
	}

	if resource.APIVersion != "stoa.io/v1" {
		t.Errorf("APIVersion = %q, want %q", resource.APIVersion, "stoa.io/v1")
	}
	if resource.Kind != "API" {
		t.Errorf("Kind = %q, want %q", resource.Kind, "API")
	}
	if resource.Metadata.Name != "petstore-api" {
		t.Errorf("Metadata.Name = %q, want %q", resource.Metadata.Name, "petstore-api")
	}
	if resource.Metadata.Labels["app"] != "petstore" {
		t.Errorf("Metadata.Labels[app] = %q, want %q", resource.Metadata.Labels["app"], "petstore")
	}

	// Spec is stored as any (interface{})
	if resource.Spec == nil {
		t.Error("Spec is nil")
	}
}

// TestEmptyAPIListResponse tests empty list response
func TestEmptyAPIListResponse(t *testing.T) {
	jsonData := `{"items": [], "totalCount": 0}`

	var response APIListResponse
	err := json.Unmarshal([]byte(jsonData), &response)
	if err != nil {
		t.Fatalf("json.Unmarshal() error = %v", err)
	}

	if response.TotalCount != 0 {
		t.Errorf("TotalCount = %d, want 0", response.TotalCount)
	}
	if len(response.Items) != 0 {
		t.Errorf("Items length = %d, want 0", len(response.Items))
	}
}
