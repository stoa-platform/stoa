// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package bridge

import (
	"context"
	"fmt"
	"os"

	"github.com/getkin/kin-openapi/openapi3"
)

// ParseResult holds the parsed OpenAPI spec and metadata
type ParseResult struct {
	Doc     *openapi3.T
	Title   string
	Version string
}

// ParseOpenAPIFile loads and validates an OpenAPI 3.x spec from a file
func ParseOpenAPIFile(path string) (*ParseResult, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read spec file: %w", err)
	}

	return ParseOpenAPI(data)
}

// ParseOpenAPI loads and validates an OpenAPI 3.x spec from bytes
func ParseOpenAPI(data []byte) (*ParseResult, error) {
	loader := openapi3.NewLoader()
	loader.IsExternalRefsAllowed = true

	doc, err := loader.LoadFromData(data)
	if err != nil {
		return nil, fmt.Errorf("failed to parse OpenAPI spec: %w", err)
	}

	// Validate the spec
	if err := doc.Validate(context.Background()); err != nil {
		return nil, fmt.Errorf("invalid OpenAPI spec: %w", err)
	}

	title := "Untitled API"
	version := "1.0.0"
	if doc.Info != nil {
		if doc.Info.Title != "" {
			title = doc.Info.Title
		}
		if doc.Info.Version != "" {
			version = doc.Info.Version
		}
	}

	return &ParseResult{
		Doc:     doc,
		Title:   title,
		Version: version,
	}, nil
}

// BaseURL extracts the first server URL from the spec, or returns empty string
func BaseURL(doc *openapi3.T) string {
	if len(doc.Servers) > 0 && doc.Servers[0].URL != "" {
		return doc.Servers[0].URL
	}
	return ""
}
