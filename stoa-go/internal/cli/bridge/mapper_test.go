// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package bridge

import (
	"testing"

	"github.com/stoa-platform/stoa-go/pkg/types"
)

const minimalSpec = `{
  "openapi": "3.0.0",
  "info": { "title": "Test API", "version": "1.0.0" },
  "servers": [{ "url": "https://api.example.com/v1" }],
  "paths": {
    "/pets": {
      "get": {
        "operationId": "listPets",
        "summary": "List all pets",
        "tags": ["pets"],
        "parameters": [
          {
            "name": "limit",
            "in": "query",
            "schema": { "type": "integer", "maximum": 100 }
          }
        ],
        "responses": { "200": { "description": "OK" } }
      },
      "post": {
        "operationId": "createPet",
        "summary": "Create a pet",
        "tags": ["pets"],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "name": { "type": "string" },
                  "tag": { "type": "string" }
                },
                "required": ["name"]
              }
            }
          }
        },
        "responses": { "201": { "description": "Created" } }
      }
    },
    "/pets/{petId}": {
      "get": {
        "operationId": "getPetById",
        "summary": "Get a pet by ID",
        "tags": ["pets"],
        "parameters": [
          {
            "name": "petId",
            "in": "path",
            "required": true,
            "schema": { "type": "string" }
          }
        ],
        "responses": { "200": { "description": "OK" } }
      }
    }
  }
}`

const securitySpec = `{
  "openapi": "3.0.0",
  "info": { "title": "Secured API", "version": "1.0.0" },
  "servers": [{ "url": "https://api.example.com" }],
  "security": [{ "bearerAuth": [] }],
  "paths": {
    "/items": {
      "get": {
        "operationId": "listItems",
        "summary": "List items",
        "responses": { "200": { "description": "OK" } }
      }
    },
    "/public": {
      "get": {
        "operationId": "publicEndpoint",
        "summary": "Public endpoint",
        "security": [],
        "responses": { "200": { "description": "OK" } }
      }
    }
  },
  "components": {
    "securitySchemes": {
      "bearerAuth": {
        "type": "http",
        "scheme": "bearer"
      }
    }
  }
}`

const apiKeySpec = `{
  "openapi": "3.0.0",
  "info": { "title": "API Key API", "version": "1.0.0" },
  "servers": [{ "url": "https://api.example.com" }],
  "security": [{ "apiKeyAuth": [] }],
  "paths": {
    "/data": {
      "get": {
        "operationId": "getData",
        "summary": "Get data",
        "responses": { "200": { "description": "OK" } }
      }
    }
  },
  "components": {
    "securitySchemes": {
      "apiKeyAuth": {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key"
      }
    }
  }
}`

const noOperationIDSpec = `{
  "openapi": "3.0.0",
  "info": { "title": "No OpID API", "version": "1.0.0" },
  "servers": [{ "url": "https://api.example.com" }],
  "paths": {
    "/users/{userId}/orders": {
      "parameters": [
        {
          "name": "userId",
          "in": "path",
          "required": true,
          "schema": { "type": "string" }
        }
      ],
      "get": {
        "summary": "Get user orders",
        "responses": { "200": { "description": "OK" } }
      }
    }
  }
}`

const oneOfSpec = `{
  "openapi": "3.0.0",
  "info": { "title": "OneOf API", "version": "1.0.0" },
  "servers": [{ "url": "https://api.example.com" }],
  "paths": {
    "/events": {
      "post": {
        "operationId": "createEvent",
        "summary": "Create event",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "oneOf": [
                  {
                    "type": "object",
                    "properties": {
                      "type": { "type": "string" },
                      "message": { "type": "string" }
                    },
                    "required": ["type"]
                  },
                  {
                    "type": "object",
                    "properties": {
                      "code": { "type": "integer" }
                    }
                  }
                ]
              }
            }
          }
        },
        "responses": { "201": { "description": "Created" } }
      }
    }
  }
}`

func TestMapOperationsToTools_SimpleGet(t *testing.T) {
	parsed, err := ParseOpenAPI([]byte(minimalSpec))
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}

	result := MapOperationsToTools(parsed.Doc, MapOptions{
		Namespace:  "tenant-acme",
		SourceSpec: "petstore",
	})

	if len(result.Tools) != 3 {
		t.Fatalf("expected 3 tools, got %d", len(result.Tools))
	}

	// Find listPets tool
	var listPets *toolForTest
	for _, tool := range result.Tools {
		if tool.Metadata.Name == "list-pets" {
			lp := toolForTest(tool)
			listPets = &lp
			break
		}
	}
	if listPets == nil {
		t.Fatal("list-pets tool not found")
	}

	if listPets.Metadata.Namespace != "tenant-acme" {
		t.Errorf("namespace = %q, want tenant-acme", listPets.Metadata.Namespace)
	}
	if listPets.APIVersion != "gostoa.dev/v1alpha1" {
		t.Errorf("apiVersion = %q, want gostoa.dev/v1alpha1", listPets.APIVersion)
	}
	if listPets.Kind != "Tool" {
		t.Errorf("kind = %q, want Tool", listPets.Kind)
	}

	spec := listPets.Spec.(types.ToolSpec)
	if spec.DisplayName != "List all pets" {
		t.Errorf("displayName = %q, want 'List all pets'", spec.DisplayName)
	}
	if spec.Method != "GET" {
		t.Errorf("method = %q, want GET", spec.Method)
	}
	if spec.Endpoint != "https://api.example.com/v1/pets" {
		t.Errorf("endpoint = %q, want https://api.example.com/v1/pets", spec.Endpoint)
	}
	if spec.Timeout != "30s" {
		t.Errorf("timeout = %q, want 30s", spec.Timeout)
	}
	if spec.Enabled == nil || !*spec.Enabled {
		t.Error("enabled should be true")
	}

	// Check inputSchema has limit property
	if spec.InputSchema == nil {
		t.Fatal("inputSchema is nil")
	}
	props, ok := spec.InputSchema["properties"].(map[string]any)
	if !ok {
		t.Fatal("inputSchema.properties missing")
	}
	if _, ok := props["limit"]; !ok {
		t.Error("inputSchema.properties should have 'limit'")
	}

	// Check labels
	if listPets.Metadata.Labels["generated-by"] != "stoactl-bridge" {
		t.Error("missing generated-by label")
	}
	if listPets.Metadata.Labels["source-spec"] != "petstore" {
		t.Error("missing source-spec label")
	}
}

func TestMapOperationsToTools_PostWithBody(t *testing.T) {
	parsed, err := ParseOpenAPI([]byte(minimalSpec))
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}

	result := MapOperationsToTools(parsed.Doc, MapOptions{Namespace: "test"})

	var createPet *toolForTest
	for _, tool := range result.Tools {
		if tool.Metadata.Name == "create-pet" {
			cp := toolForTest(tool)
			createPet = &cp
			break
		}
	}
	if createPet == nil {
		t.Fatal("create-pet tool not found")
	}

	spec := createPet.Spec.(types.ToolSpec)
	if spec.Method != "POST" {
		t.Errorf("method = %q, want POST", spec.Method)
	}
	if spec.InputSchema == nil {
		t.Fatal("inputSchema is nil")
	}

	// Check body properties merged into inputSchema
	props, ok := spec.InputSchema["properties"].(map[string]any)
	if !ok {
		t.Fatal("inputSchema.properties missing")
	}
	if _, ok := props["name"]; !ok {
		t.Error("inputSchema should have 'name' from request body")
	}
	if _, ok := props["tag"]; !ok {
		t.Error("inputSchema should have 'tag' from request body")
	}

	// Check required includes body required fields
	required, ok := spec.InputSchema["required"].([]any)
	if !ok {
		t.Fatal("inputSchema.required missing")
	}
	found := false
	for _, r := range required {
		if r == "name" {
			found = true
			break
		}
	}
	if !found {
		t.Error("required should include 'name'")
	}
}

func TestMapOperationsToTools_PathParams(t *testing.T) {
	parsed, err := ParseOpenAPI([]byte(minimalSpec))
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}

	result := MapOperationsToTools(parsed.Doc, MapOptions{Namespace: "test"})

	var getPet *toolForTest
	for _, tool := range result.Tools {
		if tool.Metadata.Name == "get-pet-by-id" {
			gp := toolForTest(tool)
			getPet = &gp
			break
		}
	}
	if getPet == nil {
		t.Fatal("get-pet-by-id tool not found")
	}

	spec := getPet.Spec.(types.ToolSpec)
	if spec.Endpoint != "https://api.example.com/v1/pets/{petId}" {
		t.Errorf("endpoint = %q, want https://api.example.com/v1/pets/{petId}", spec.Endpoint)
	}

	// Path params should be in required
	if spec.InputSchema == nil {
		t.Fatal("inputSchema is nil")
	}
	required, ok := spec.InputSchema["required"].([]any)
	if !ok {
		t.Fatal("inputSchema.required missing")
	}
	found := false
	for _, r := range required {
		if r == "petId" {
			found = true
			break
		}
	}
	if !found {
		t.Error("required should include 'petId' (path param)")
	}
}

func TestMapOperationsToTools_BearerAuth(t *testing.T) {
	parsed, err := ParseOpenAPI([]byte(securitySpec))
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}

	result := MapOperationsToTools(parsed.Doc, MapOptions{Namespace: "test"})

	var listItems *toolForTest
	for _, tool := range result.Tools {
		if tool.Metadata.Name == "list-items" {
			li := toolForTest(tool)
			listItems = &li
			break
		}
	}
	if listItems == nil {
		t.Fatal("list-items tool not found")
	}

	spec := listItems.Spec.(types.ToolSpec)
	if spec.Authentication == nil {
		t.Fatal("authentication is nil, expected bearer")
	}
	if spec.Authentication.Type != "bearer" {
		t.Errorf("auth type = %q, want bearer", spec.Authentication.Type)
	}
}

func TestMapOperationsToTools_ApiKeyAuth(t *testing.T) {
	parsed, err := ParseOpenAPI([]byte(apiKeySpec))
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}

	result := MapOperationsToTools(parsed.Doc, MapOptions{Namespace: "test"})

	if len(result.Tools) != 1 {
		t.Fatalf("expected 1 tool, got %d", len(result.Tools))
	}

	spec := result.Tools[0].Spec.(types.ToolSpec)
	if spec.Authentication == nil {
		t.Fatal("authentication is nil")
	}
	if spec.Authentication.Type != "apiKey" {
		t.Errorf("auth type = %q, want apiKey", spec.Authentication.Type)
	}
	if spec.Authentication.HeaderName != "X-API-Key" {
		t.Errorf("headerName = %q, want X-API-Key", spec.Authentication.HeaderName)
	}
}

func TestMapOperationsToTools_AuthSecretOverride(t *testing.T) {
	parsed, err := ParseOpenAPI([]byte(securitySpec))
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}

	result := MapOperationsToTools(parsed.Doc, MapOptions{
		Namespace:  "test",
		AuthSecret: "my-api-secret",
	})

	var listItems *toolForTest
	for _, tool := range result.Tools {
		if tool.Metadata.Name == "list-items" {
			li := toolForTest(tool)
			listItems = &li
			break
		}
	}
	if listItems == nil {
		t.Fatal("list-items tool not found")
	}

	spec := listItems.Spec.(types.ToolSpec)
	if spec.Authentication == nil {
		t.Fatal("authentication is nil")
	}
	if spec.Authentication.Type != "bearer" {
		t.Errorf("auth type = %q, want bearer", spec.Authentication.Type)
	}
	if spec.Authentication.SecretRef == nil {
		t.Fatal("secretRef is nil")
	}
	if spec.Authentication.SecretRef.Name != "my-api-secret" {
		t.Errorf("secretRef.name = %q, want my-api-secret", spec.Authentication.SecretRef.Name)
	}
}

func TestMapOperationsToTools_NoOperationID(t *testing.T) {
	parsed, err := ParseOpenAPI([]byte(noOperationIDSpec))
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}

	result := MapOperationsToTools(parsed.Doc, MapOptions{Namespace: "test"})

	if len(result.Tools) != 1 {
		t.Fatalf("expected 1 tool, got %d", len(result.Tools))
	}

	// Generated name from method + path: get-users-user-id-orders
	name := result.Tools[0].Metadata.Name
	if name != "get-users-user-id-orders" {
		t.Errorf("name = %q, want get-users-user-id-orders", name)
	}
}

func TestMapOperationsToTools_OneOfWarning(t *testing.T) {
	parsed, err := ParseOpenAPI([]byte(oneOfSpec))
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}

	result := MapOperationsToTools(parsed.Doc, MapOptions{Namespace: "test"})

	if len(result.Tools) != 1 {
		t.Fatalf("expected 1 tool, got %d", len(result.Tools))
	}

	// Should have a warning about oneOf
	if len(result.Warnings) == 0 {
		t.Error("expected oneOf warning")
	}
	foundOneOfWarning := false
	for _, w := range result.Warnings {
		if w == "oneOf schema detected — using first variant" {
			foundOneOfWarning = true
			break
		}
	}
	if !foundOneOfWarning {
		t.Errorf("expected oneOf warning, got: %v", result.Warnings)
	}

	// First variant should be used (has 'type' and 'message' properties)
	spec := result.Tools[0].Spec.(types.ToolSpec)
	if spec.InputSchema != nil {
		props, ok := spec.InputSchema["properties"].(map[string]any)
		if ok {
			if _, ok := props["type"]; !ok {
				t.Error("expected 'type' property from first oneOf variant")
			}
		}
	}
}

func TestMapOperationsToTools_IncludeTags(t *testing.T) {
	parsed, err := ParseOpenAPI([]byte(minimalSpec))
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}

	result := MapOperationsToTools(parsed.Doc, MapOptions{
		Namespace:   "test",
		IncludeTags: []string{"nonexistent"},
	})

	if len(result.Tools) != 0 {
		t.Errorf("expected 0 tools with nonexistent tag, got %d", len(result.Tools))
	}

	// Now include the actual tag
	result2 := MapOperationsToTools(parsed.Doc, MapOptions{
		Namespace:   "test",
		IncludeTags: []string{"pets"},
	})
	if len(result2.Tools) != 3 {
		t.Errorf("expected 3 tools with pets tag, got %d", len(result2.Tools))
	}
}

func TestMapOperationsToTools_ExcludeTags(t *testing.T) {
	parsed, err := ParseOpenAPI([]byte(minimalSpec))
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}

	result := MapOperationsToTools(parsed.Doc, MapOptions{
		Namespace:   "test",
		ExcludeTags: []string{"pets"},
	})

	if len(result.Tools) != 0 {
		t.Errorf("expected 0 tools after excluding pets tag, got %d", len(result.Tools))
	}
}

func TestMapOperationsToTools_IncludeOps(t *testing.T) {
	parsed, err := ParseOpenAPI([]byte(minimalSpec))
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}

	result := MapOperationsToTools(parsed.Doc, MapOptions{
		Namespace:  "test",
		IncludeOps: []string{"listPets", "createPet"},
	})

	if len(result.Tools) != 2 {
		t.Errorf("expected 2 tools, got %d", len(result.Tools))
	}
}

func TestMapOperationsToTools_BaseURLOverride(t *testing.T) {
	parsed, err := ParseOpenAPI([]byte(minimalSpec))
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}

	result := MapOperationsToTools(parsed.Doc, MapOptions{
		Namespace: "test",
		BaseURL:   "https://internal.api.com",
	})

	for _, tool := range result.Tools {
		spec := tool.Spec.(types.ToolSpec)
		if spec.Endpoint[:25] != "https://internal.api.com/" {
			t.Errorf("endpoint = %q, expected to start with https://internal.api.com/", spec.Endpoint)
		}
	}
}

func TestToolName_KebabCase(t *testing.T) {
	tests := []struct {
		opID   string
		method string
		path   string
		want   string
	}{
		{"listPets", "GET", "/pets", "list-pets"},
		{"createPet", "POST", "/pets", "create-pet"},
		{"getPetById", "GET", "/pets/{petId}", "get-pet-by-id"},
		{"", "GET", "/pets/{petId}/toys", "get-pets-pet-id-toys"},
		{"", "POST", "/users", "post-users"},
		{"getAPIKeys", "GET", "/keys", "get-apikeys"},
		{"list_all_items", "GET", "/items", "list-all-items"},
	}

	for _, tt := range tests {
		got := toolName(tt.opID, tt.method, tt.path)
		if got != tt.want {
			t.Errorf("toolName(%q, %q, %q) = %q, want %q", tt.opID, tt.method, tt.path, got, tt.want)
		}
	}
}

func TestBaseURL(t *testing.T) {
	parsed, err := ParseOpenAPI([]byte(minimalSpec))
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	url := BaseURL(parsed.Doc)
	if url != "https://api.example.com/v1" {
		t.Errorf("BaseURL = %q, want https://api.example.com/v1", url)
	}
}

// toolForTest is a type alias to avoid import cycles
type toolForTest = types.Resource
