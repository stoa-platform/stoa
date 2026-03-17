// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package bridge

import (
	"fmt"
	"regexp"
	"strings"

	"github.com/getkin/kin-openapi/openapi3"

	"github.com/stoa-platform/stoa-go/pkg/output"
	"github.com/stoa-platform/stoa-go/pkg/types"
)

// MapOptions configures the OpenAPI-to-Tool mapping
type MapOptions struct {
	Namespace   string
	BaseURL     string // Override servers[0].url
	AuthSecret  string // Secret name for auth
	Timeout     string // Default timeout
	SourceSpec  string // Label value for source-spec
	IncludeTags []string
	ExcludeTags []string
	IncludeOps  []string
}

// MapResult holds the generated Tool resources
type MapResult struct {
	Tools    []types.Resource
	Warnings []string
}

// MapOperationsToTools converts OpenAPI operations to Tool CRD resources
func MapOperationsToTools(doc *openapi3.T, opts MapOptions) *MapResult {
	result := &MapResult{}

	baseURL := opts.BaseURL
	if baseURL == "" {
		baseURL = BaseURL(doc)
	}
	// Strip trailing slash
	baseURL = strings.TrimRight(baseURL, "/")

	if opts.Timeout == "" {
		opts.Timeout = "30s"
	}

	for path, pathItem := range doc.Paths.Map() {
		operations := map[string]*openapi3.Operation{
			"GET":    pathItem.Get,
			"POST":   pathItem.Post,
			"PUT":    pathItem.Put,
			"PATCH":  pathItem.Patch,
			"DELETE": pathItem.Delete,
		}

		for method, op := range operations {
			if op == nil {
				continue
			}

			if !shouldIncludeOperation(op, opts) {
				continue
			}

			tool, warnings := mapOperation(doc, path, method, op, pathItem.Parameters, baseURL, opts)
			result.Tools = append(result.Tools, tool)
			result.Warnings = append(result.Warnings, warnings...)
		}
	}

	return result
}

func shouldIncludeOperation(op *openapi3.Operation, opts MapOptions) bool {
	// Filter by operationId
	if len(opts.IncludeOps) > 0 {
		found := false
		for _, id := range opts.IncludeOps {
			if op.OperationID == id {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}

	// Filter by tags
	if len(opts.IncludeTags) > 0 {
		found := false
		for _, tag := range op.Tags {
			for _, include := range opts.IncludeTags {
				if tag == include {
					found = true
					break
				}
			}
		}
		if !found {
			return false
		}
	}

	if len(opts.ExcludeTags) > 0 {
		for _, tag := range op.Tags {
			for _, exclude := range opts.ExcludeTags {
				if tag == exclude {
					return false
				}
			}
		}
	}

	return true
}

func mapOperation(doc *openapi3.T, path, method string, op *openapi3.Operation, pathParams openapi3.Parameters, baseURL string, opts MapOptions) (types.Resource, []string) {
	var warnings []string

	// Tool name: operationId (kebab-case) or generated from method+path
	name := toolName(op.OperationID, method, path)

	// Display name: summary or generated
	displayName := op.Summary
	if displayName == "" {
		displayName = fmt.Sprintf("%s %s", method, path)
	}
	if len(displayName) > 64 {
		displayName = displayName[:64]
	}

	// Description
	description := op.Description
	if description == "" {
		description = displayName
	}
	if len(description) > 1024 {
		description = description[:1024]
	}

	// Endpoint
	endpoint := baseURL + path

	// Build input schema from parameters + request body
	inputSchema := buildInputSchema(op, pathParams, &warnings)

	// Authentication from security requirements
	var authConfig *types.AuthConfig
	if opts.AuthSecret != "" {
		authConfig = &types.AuthConfig{
			Type: "bearer",
			SecretRef: &types.SecretRef{
				Name: opts.AuthSecret,
				Key:  "token",
			},
		}
	} else {
		authConfig = extractAuth(doc, op, &warnings)
	}

	// Labels
	labels := map[string]string{
		"generated-by": "stoactl-bridge",
	}
	if opts.SourceSpec != "" {
		labels["source-spec"] = opts.SourceSpec
	}

	// APIRef for traceability
	apiRef := &types.APIRef{
		Name:        opts.SourceSpec,
		OperationID: op.OperationID,
	}
	if doc.Info != nil {
		apiRef.Version = doc.Info.Version
	}

	enabled := types.BoolPtr(true)

	spec := types.ToolSpec{
		DisplayName:    displayName,
		Description:    description,
		Endpoint:       endpoint,
		Method:         method,
		InputSchema:    inputSchema,
		Tags:           op.Tags,
		Timeout:        opts.Timeout,
		Enabled:        enabled,
		Authentication: authConfig,
		APIRef:         apiRef,
	}

	resource := types.Resource{
		APIVersion: types.ToolCRDAPIVersion,
		Kind:       types.ToolCRDKind,
		Metadata: types.Metadata{
			Name:      name,
			Namespace: opts.Namespace,
			Labels:    labels,
		},
		Spec: spec,
	}

	return resource, warnings
}

func buildInputSchema(op *openapi3.Operation, pathParams openapi3.Parameters, warnings *[]string) map[string]any {
	properties := map[string]any{}
	var required []string

	// Collect all parameters (path-level + operation-level)
	allParams := append(pathParams, op.Parameters...)
	for _, paramRef := range allParams {
		if paramRef == nil || paramRef.Value == nil {
			continue
		}
		param := paramRef.Value

		// Skip header/cookie params (not typically exposed as tool inputs)
		if param.In == "header" || param.In == "cookie" {
			continue
		}

		propSchema := schemaToMap(param.Schema)
		if propSchema != nil {
			properties[param.Name] = propSchema
		}

		if param.Required || param.In == "path" {
			required = append(required, param.Name)
		}
	}

	// Merge request body schema
	if op.RequestBody != nil && op.RequestBody.Value != nil {
		body := op.RequestBody.Value
		jsonContent := body.Content.Get("application/json")
		if jsonContent != nil && jsonContent.Schema != nil {
			bodySchema := schemaRefToMap(jsonContent.Schema, warnings)
			if bodyProps, ok := bodySchema["properties"].(map[string]any); ok {
				for k, v := range bodyProps {
					properties[k] = v
				}
			}
			if bodyReq, ok := bodySchema["required"].([]any); ok {
				for _, r := range bodyReq {
					if s, ok := r.(string); ok {
						required = append(required, s)
					}
				}
			}
		} else if body.Content.Get("application/json") == nil && len(body.Content) > 0 {
			*warnings = append(*warnings, "operation has request body but no application/json content type, skipping body")
		}
	}

	if len(properties) == 0 {
		return nil
	}

	schema := map[string]any{
		"type":       "object",
		"properties": properties,
	}
	if len(required) > 0 {
		schema["required"] = dedup(required)
	}

	return schema
}

func schemaRefToMap(ref *openapi3.SchemaRef, warnings *[]string) map[string]any {
	if ref == nil || ref.Value == nil {
		return nil
	}

	schema := ref.Value

	// Handle oneOf/anyOf — use first variant, warn
	if len(schema.OneOf) > 0 {
		*warnings = append(*warnings, "oneOf schema detected — using first variant")
		output.Info("Warning: oneOf schema detected, using first variant. Review generated tools for accuracy.")
		return schemaRefToMap(schema.OneOf[0], warnings)
	}
	if len(schema.AnyOf) > 0 {
		*warnings = append(*warnings, "anyOf schema detected — using first variant")
		output.Info("Warning: anyOf schema detected, using first variant. Review generated tools for accuracy.")
		return schemaRefToMap(schema.AnyOf[0], warnings)
	}

	return schemaValueToMap(schema)
}

func schemaValueToMap(schema *openapi3.Schema) map[string]any {
	if schema == nil {
		return nil
	}

	result := map[string]any{}

	if schema.Type != nil {
		types := schema.Type.Slice()
		if len(types) == 1 {
			result["type"] = types[0]
		} else if len(types) > 1 {
			result["type"] = types
		}
	}

	if schema.Description != "" {
		result["description"] = schema.Description
	}

	if len(schema.Enum) > 0 {
		result["enum"] = schema.Enum
	}

	if schema.Format != "" {
		result["format"] = schema.Format
	}

	if schema.Max != nil {
		result["maximum"] = *schema.Max
	}
	if schema.Min != nil {
		result["minimum"] = *schema.Min
	}
	if schema.MaxLength != nil {
		result["maxLength"] = *schema.MaxLength
	}
	if schema.MinLength != 0 {
		result["minLength"] = schema.MinLength
	}

	if schema.Default != nil {
		result["default"] = schema.Default
	}

	// Object properties
	if len(schema.Properties) > 0 {
		props := map[string]any{}
		for name, propRef := range schema.Properties {
			propMap := schemaValueToMap(propRef.Value)
			if propMap != nil {
				props[name] = propMap
			}
		}
		result["properties"] = props
	}

	if len(schema.Required) > 0 {
		reqSlice := make([]any, len(schema.Required))
		for i, r := range schema.Required {
			reqSlice[i] = r
		}
		result["required"] = reqSlice
	}

	// Array items
	if schema.Items != nil && schema.Items.Value != nil {
		result["items"] = schemaValueToMap(schema.Items.Value)
	}

	return result
}

func schemaToMap(ref *openapi3.SchemaRef) map[string]any {
	if ref == nil || ref.Value == nil {
		return nil
	}
	return schemaValueToMap(ref.Value)
}

func extractAuth(doc *openapi3.T, op *openapi3.Operation, warnings *[]string) *types.AuthConfig {
	// Check operation-level security first, then global
	security := op.Security
	if security == nil {
		security = &doc.Security
	}
	if security == nil || len(*security) == 0 {
		return nil
	}

	// Use first security requirement
	firstReq := (*security)[0]
	for schemeName := range firstReq {
		if doc.Components == nil || doc.Components.SecuritySchemes == nil {
			continue
		}
		schemeRef, ok := doc.Components.SecuritySchemes[schemeName]
		if !ok || schemeRef.Value == nil {
			continue
		}
		scheme := schemeRef.Value

		switch scheme.Type {
		case "http":
			if scheme.Scheme == "bearer" {
				return &types.AuthConfig{Type: "bearer"}
			}
			return &types.AuthConfig{Type: "basic"}
		case "apiKey":
			return &types.AuthConfig{
				Type:       "apiKey",
				HeaderName: scheme.Name,
			}
		case "oauth2", "openIdConnect":
			return &types.AuthConfig{Type: "oauth2"}
		}
	}

	return nil
}

// toolName generates a kebab-case tool name from operationId or method+path
func toolName(operationID, method, path string) string {
	if operationID != "" {
		return toKebabCase(operationID)
	}

	// Generate from method + path segments
	// /pets/{petId}/toys → pets-pet-id-toys
	segments := strings.Split(strings.Trim(path, "/"), "/")
	var parts []string
	for _, seg := range segments {
		// Remove braces from path params
		seg = strings.TrimPrefix(seg, "{")
		seg = strings.TrimSuffix(seg, "}")
		parts = append(parts, toKebabCase(seg))
	}

	return strings.ToLower(method) + "-" + strings.Join(parts, "-")
}

var camelCaseRe = regexp.MustCompile(`([a-z0-9])([A-Z])`)

func toKebabCase(s string) string {
	// Convert camelCase to kebab-case
	s = camelCaseRe.ReplaceAllString(s, "${1}-${2}")
	s = strings.ToLower(s)
	// Replace underscores and spaces with hyphens
	s = strings.ReplaceAll(s, "_", "-")
	s = strings.ReplaceAll(s, " ", "-")
	// Remove consecutive hyphens
	for strings.Contains(s, "--") {
		s = strings.ReplaceAll(s, "--", "-")
	}
	return strings.Trim(s, "-")
}

func dedup(s []string) []any {
	seen := map[string]bool{}
	var result []any
	for _, v := range s {
		if !seen[v] {
			seen[v] = true
			result = append(result, v)
		}
	}
	return result
}
