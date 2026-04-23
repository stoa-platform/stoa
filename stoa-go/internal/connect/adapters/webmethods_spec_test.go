package adapters

import (
	"encoding/json"
	"testing"
)

func TestWebMethodsOpenAPI31Downgrade(t *testing.T) {
	// GO-1 L.2: downgradeOpenAPI31 now parses JSON instead of regex-matching,
	// so the output key ordering and whitespace may differ from the input.
	// Assert on the parsed value of the `openapi` field only.
	check := func(t *testing.T, in []byte, wantVersion string) {
		t.Helper()
		out := downgradeOpenAPI31(in)
		var m map[string]interface{}
		if err := json.Unmarshal(out, &m); err != nil {
			t.Fatalf("parse: %v; out=%s", err, string(out))
		}
		if got := m["openapi"]; got != wantVersion {
			t.Errorf("openapi: got %v, want %q", got, wantVersion)
		}
	}

	check(t, []byte(`{"openapi": "3.1.0", "info": {"title": "Test"}}`), "3.0.3")
	check(t, []byte(`{"openapi": "3.1.1", "info": {"title": "Test"}}`), "3.0.3")
	check(t, []byte(`{"openapi": "3.0.2", "info": {"title": "Test"}}`), "3.0.2")
	check(t, []byte(`{"openapi": "2.0", "info": {"title": "Test"}}`), "2.0")
}

// TestRegressionStripResponseSchemasSwagger2 — CAB-1944 regression guard:
// webMethods RefProperty parser crashes on $ref in Swagger 2.0 response
// schemas. Renamed from TestRegressionStripSwagger2ResponseRefs in GO-1
// H.3 (BUG-REPORT-GO-1.md) to reflect the broader scope now that the
// function also handles OpenAPI 3.x responses.
func TestRegressionStripResponseSchemasSwagger2(t *testing.T) {
	spec := []byte(`{"swagger":"2.0","paths":{"/pet/findByStatus":{"get":{"responses":{"200":{"description":"ok","schema":{"type":"array","items":{"$ref":"#/definitions/Pet"}}}}}}}}`)
	result := stripResponseSchemas(spec)

	var parsed map[string]interface{}
	if err := json.Unmarshal(result, &parsed); err != nil {
		t.Fatalf("parse error: %v", err)
	}

	paths := parsed["paths"].(map[string]interface{})
	get := paths["/pet/findByStatus"].(map[string]interface{})["get"].(map[string]interface{})
	resp200 := get["responses"].(map[string]interface{})["200"].(map[string]interface{})
	if _, hasSchema := resp200["schema"]; hasSchema {
		t.Error("Swagger 2.0 response schema should have been stripped")
	}
}

// TestRegressionStripResponseSchemasOpenAPI3 — CAB-1944 / GO-1 H.3: the
// function now strips OpenAPI 3.x content schemas too. Pre-H.3 this was
// asserted as a no-op (function covered only Swagger 2.0), but webMethods
// 10.15 RefProperty crashes on $ref in 3.x response content schemas the
// same way.
func TestRegressionStripResponseSchemasOpenAPI3(t *testing.T) {
	spec := []byte(`{"openapi":"3.0.0","paths":{"/pet":{"get":{"responses":{"200":{"content":{"application/json":{"schema":{"$ref":"#/components/schemas/Pet"}}}}}}}}}`)
	result := stripResponseSchemas(spec)

	var parsed map[string]interface{}
	if err := json.Unmarshal(result, &parsed); err != nil {
		t.Fatalf("parse error: %v", err)
	}

	paths := parsed["paths"].(map[string]interface{})
	get := paths["/pet"].(map[string]interface{})["get"].(map[string]interface{})
	resp200 := get["responses"].(map[string]interface{})["200"].(map[string]interface{})
	content, ok := resp200["content"].(map[string]interface{})
	if !ok {
		t.Fatalf("content missing: %v", resp200)
	}
	mt := content["application/json"].(map[string]interface{})
	if _, hasSchema := mt["schema"]; hasSchema {
		t.Error("OpenAPI 3.x response content schema should have been stripped")
	}
}
