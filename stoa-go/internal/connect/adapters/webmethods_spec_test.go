package adapters

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestWebMethodsOpenAPI31Downgrade(t *testing.T) {
	spec31 := []byte(`{"openapi": "3.1.0", "info": {"title": "Test"}}`)
	result := downgradeOpenAPI31(spec31)
	expected := `{"openapi": "3.0.3", "info": {"title": "Test"}}`
	if string(result) != expected {
		t.Errorf("expected %s, got %s", expected, string(result))
	}

	spec311 := []byte(`{"openapi": "3.1.1", "info": {"title": "Test"}}`)
	result311 := downgradeOpenAPI31(spec311)
	if !strings.Contains(string(result311), `"3.0.3"`) {
		t.Errorf("expected 3.0.3, got %s", string(result311))
	}

	spec30 := []byte(`{"openapi": "3.0.2", "info": {"title": "Test"}}`)
	result30 := downgradeOpenAPI31(spec30)
	if string(result30) != string(spec30) {
		t.Errorf("expected 3.0.2 unchanged, got %s", string(result30))
	}
}

// TestRegressionStripSwagger2ResponseRefs — CAB-1944: webMethods RefProperty crash on $ref in response schemas.
func TestRegressionStripSwagger2ResponseRefs(t *testing.T) {
	spec := []byte(`{"swagger":"2.0","paths":{"/pet/findByStatus":{"get":{"responses":{"200":{"description":"ok","schema":{"type":"array","items":{"$ref":"#/definitions/Pet"}}}}}}}}`)
	result := stripSwagger2ResponseRefs(spec)

	var parsed map[string]interface{}
	if err := json.Unmarshal(result, &parsed); err != nil {
		t.Fatalf("parse error: %v", err)
	}

	paths := parsed["paths"].(map[string]interface{})
	get := paths["/pet/findByStatus"].(map[string]interface{})["get"].(map[string]interface{})
	resp200 := get["responses"].(map[string]interface{})["200"].(map[string]interface{})
	if _, hasSchema := resp200["schema"]; hasSchema {
		t.Error("schema with $ref should have been stripped")
	}
}

func TestRegressionStripSwagger2ResponseRefsNoOpOpenAPI3(t *testing.T) {
	// No-op for OpenAPI 3.x specs
	spec := []byte(`{"openapi":"3.0.0","paths":{"/pet":{"get":{"responses":{"200":{"content":{"application/json":{"schema":{"$ref":"#/components/schemas/Pet"}}}}}}}}}`)
	result := stripSwagger2ResponseRefs(spec)
	if string(result) != string(spec) {
		t.Error("should not modify OpenAPI 3.x specs")
	}
}
