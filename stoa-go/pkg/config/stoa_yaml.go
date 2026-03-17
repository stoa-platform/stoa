// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM

// Package config provides stoa.yaml declarative spec parsing (CAB-1412).
//
// stoa.yaml is the Git-first API deployment contract.  The CLI validates the
// file locally before sending the spec to the Control Plane API.
//
// Minimal example:
//
//	name: petstore
//	version: 1.2.0
//	endpoints:
//	  - path: /pets
//	    method: GET
package config

import (
	"fmt"
	"os"
	"regexp"

	"gopkg.in/yaml.v3"
)

// StoaEndpoint represents a single endpoint in stoa.yaml.
type StoaEndpoint struct {
	Path        string   `yaml:"path"`
	Method      string   `yaml:"method,omitempty"`
	Description string   `yaml:"description,omitempty"`
	Tags        []string `yaml:"tags,omitempty"`
}

// StoaRateLimit represents rate limiting config in stoa.yaml.
type StoaRateLimit struct {
	RequestsPerMinute int `yaml:"requests_per_minute"`
	Burst             int `yaml:"burst,omitempty"`
}

// StoaAuth represents authentication config in stoa.yaml.
type StoaAuth struct {
	Type     string `yaml:"type"`
	Issuer   string `yaml:"issuer,omitempty"`
	Header   string `yaml:"header,omitempty"`
	Required bool   `yaml:"required"`
}

// StoaYamlSpec is the root model for the stoa.yaml declarative API spec.
// It mirrors the StoaYamlSpec Pydantic model in the Control Plane API.
type StoaYamlSpec struct {
	Name      string         `yaml:"name"`
	Version   string         `yaml:"version,omitempty"`
	Endpoints []StoaEndpoint `yaml:"endpoints,omitempty"`
	RateLimit *StoaRateLimit `yaml:"rate_limit,omitempty"`
	Auth      *StoaAuth      `yaml:"auth,omitempty"`
	Tags      []string       `yaml:"tags,omitempty"`
}

var versionPattern = regexp.MustCompile(`^\d+\.\d+\.\d+`)

var validAuthTypes = map[string]bool{
	"jwt":     true,
	"api_key": true,
	"mtls":    true,
	"oauth2":  true,
	"none":    true,
}

// LoadStoaYaml reads, parses, and validates a stoa.yaml file.
// Returns a human-readable error if validation fails.
func LoadStoaYaml(path string) (*StoaYamlSpec, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read %s: %w", path, err)
	}

	var spec StoaYamlSpec
	if err := yaml.Unmarshal(data, &spec); err != nil {
		return nil, fmt.Errorf("invalid stoa.yaml syntax in %s: %w", path, err)
	}

	if err := spec.Validate(); err != nil {
		return nil, err
	}

	return &spec, nil
}

// Validate checks required fields and format constraints.
// It also applies defaults (version → "1.0.0", endpoint method → "GET").
func (s *StoaYamlSpec) Validate() error {
	if s.Name == "" {
		return fmt.Errorf("stoa.yaml: 'name' is required")
	}
	if len(s.Name) > 255 {
		return fmt.Errorf("stoa.yaml: 'name' must be 255 characters or fewer")
	}

	if s.Version == "" {
		s.Version = "1.0.0"
	} else if !versionPattern.MatchString(s.Version) {
		return fmt.Errorf("stoa.yaml: 'version' must be a semantic version (e.g. 1.0.0), got %q", s.Version)
	}

	for i, ep := range s.Endpoints {
		if ep.Path == "" {
			return fmt.Errorf("stoa.yaml: endpoints[%d].path is required", i)
		}
		if s.Endpoints[i].Method == "" {
			s.Endpoints[i].Method = "GET"
		}
	}

	if s.RateLimit != nil && s.RateLimit.RequestsPerMinute <= 0 {
		return fmt.Errorf("stoa.yaml: rate_limit.requests_per_minute must be > 0")
	}

	if s.Auth != nil && !validAuthTypes[s.Auth.Type] {
		return fmt.Errorf("stoa.yaml: auth.type must be one of: jwt, api_key, mtls, oauth2, none — got %q", s.Auth.Type)
	}

	return nil
}
