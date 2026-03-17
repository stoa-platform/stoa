// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package types

// ToolSpec represents the spec section of a Tool CRD
type ToolSpec struct {
	DisplayName    string           `yaml:"displayName" json:"displayName"`
	Description    string           `yaml:"description" json:"description"`
	Endpoint       string           `yaml:"endpoint,omitempty" json:"endpoint,omitempty"`
	Method         string           `yaml:"method,omitempty" json:"method,omitempty"`
	InputSchema    map[string]any   `yaml:"inputSchema,omitempty" json:"inputSchema,omitempty"`
	Tags           []string         `yaml:"tags,omitempty" json:"tags,omitempty"`
	Version        string           `yaml:"version,omitempty" json:"version,omitempty"`
	Timeout        string           `yaml:"timeout,omitempty" json:"timeout,omitempty"`
	Enabled        *bool            `yaml:"enabled,omitempty" json:"enabled,omitempty"`
	Authentication *AuthConfig      `yaml:"authentication,omitempty" json:"authentication,omitempty"`
	RateLimit      *RateLimitConfig `yaml:"rateLimit,omitempty" json:"rateLimit,omitempty"`
	APIRef         *APIRef          `yaml:"apiRef,omitempty" json:"apiRef,omitempty"`
}

// AuthConfig represents authentication configuration for a Tool
type AuthConfig struct {
	Type       string     `yaml:"type" json:"type"`
	SecretRef  *SecretRef `yaml:"secretRef,omitempty" json:"secretRef,omitempty"`
	HeaderName string     `yaml:"headerName,omitempty" json:"headerName,omitempty"`
}

// SecretRef points to a Kubernetes secret
type SecretRef struct {
	Name string `yaml:"name" json:"name"`
	Key  string `yaml:"key" json:"key"`
}

// RateLimitConfig defines rate limiting for a Tool
type RateLimitConfig struct {
	RequestsPerMinute int `yaml:"requestsPerMinute" json:"requestsPerMinute"`
	Burst             int `yaml:"burst,omitempty" json:"burst,omitempty"`
}

// APIRef links a Tool to its source API
type APIRef struct {
	Name        string `yaml:"name" json:"name"`
	Version     string `yaml:"version,omitempty" json:"version,omitempty"`
	OperationID string `yaml:"operationId,omitempty" json:"operationId,omitempty"`
}

// ToolCRDAPIVersion is the API version for Tool CRDs
const ToolCRDAPIVersion = "gostoa.dev/v1alpha1"

// ToolCRDKind is the kind for Tool CRDs
const ToolCRDKind = "Tool"

// BoolPtr returns a pointer to a bool value
func BoolPtr(b bool) *bool {
	return &b
}
