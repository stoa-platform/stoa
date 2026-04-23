// regression for CAB-1944 (GO-1 audit H.2 + H.1): fixExternalDocs must walk
// the full OpenAPI tree (tags, operations, components.schemas and nested
// schemas), not just the root. Also covers removal of the dead-code call
// in webmethods_sync.go — the wrapper payload never carried externalDocs
// at top level, so the previous post-marshal application was a no-op.
package adapters

import (
	"encoding/json"
	"reflect"
	"testing"
)

// unmarshalTo is a tiny helper: decode bytes to map[string]interface{} or
// fail the test. Keeps assertions terse below.
func unmarshalTo(t *testing.T, data []byte) map[string]interface{} {
	t.Helper()
	var m map[string]interface{}
	if err := json.Unmarshal(data, &m); err != nil {
		t.Fatalf("unmarshal: %v; payload=%s", err, string(data))
	}
	return m
}

// isArrayOfOneObject returns true if v is a []interface{} containing exactly
// one map[string]interface{}.
func isArrayOfOneObject(v interface{}) bool {
	arr, ok := v.([]interface{})
	if !ok || len(arr) != 1 {
		return false
	}
	_, ok = arr[0].(map[string]interface{})
	return ok
}

// ---------------------------------------------------------------------------
// TestWebMethodsFixExternalDocs_TopLevel — baseline, preserves pre-GO-1
// behaviour for specs whose only externalDocs lives at the root.
// ---------------------------------------------------------------------------
func TestWebMethodsFixExternalDocs_TopLevel(t *testing.T) {
	in := []byte(`{"openapi":"3.0.3","info":{"title":"t","version":"1"},"externalDocs":{"url":"https://a","description":"A"}}`)
	out := fixExternalDocs(in)
	m := unmarshalTo(t, out)
	if !isArrayOfOneObject(m["externalDocs"]) {
		t.Errorf("root externalDocs not wrapped: %v", m["externalDocs"])
	}
}

// ---------------------------------------------------------------------------
// TestWebMethodsFixExternalDocs_InTags — per-tag externalDocs must wrap;
// tags that don't have externalDocs must be untouched.
// ---------------------------------------------------------------------------
func TestWebMethodsFixExternalDocs_InTags(t *testing.T) {
	in := []byte(`{"openapi":"3.0.3","info":{"title":"t","version":"1"},"tags":[{"name":"pets","externalDocs":{"url":"https://pets"}},{"name":"users"}],"paths":{}}`)
	out := fixExternalDocs(in)
	m := unmarshalTo(t, out)

	tags, ok := m["tags"].([]interface{})
	if !ok || len(tags) != 2 {
		t.Fatalf("expected 2 tags, got %v", m["tags"])
	}
	tag0 := tags[0].(map[string]interface{})
	if !isArrayOfOneObject(tag0["externalDocs"]) {
		t.Errorf("tag[0].externalDocs not wrapped: %v", tag0["externalDocs"])
	}
	tag1 := tags[1].(map[string]interface{})
	if _, has := tag1["externalDocs"]; has {
		t.Errorf("tag[1] should have no externalDocs, got %v", tag1)
	}
}

// ---------------------------------------------------------------------------
// TestWebMethodsFixExternalDocs_InOperations — Operation Object externalDocs
// (paths[*].<method>.externalDocs) must wrap.
// ---------------------------------------------------------------------------
func TestWebMethodsFixExternalDocs_InOperations(t *testing.T) {
	in := []byte(`{"openapi":"3.0.3","info":{"title":"t","version":"1"},"paths":{"/p":{"get":{"operationId":"g","externalDocs":{"url":"https://op"},"responses":{}}}}}`)
	out := fixExternalDocs(in)
	m := unmarshalTo(t, out)

	op := m["paths"].(map[string]interface{})["/p"].(map[string]interface{})["get"].(map[string]interface{})
	if !isArrayOfOneObject(op["externalDocs"]) {
		t.Errorf("operation externalDocs not wrapped: %v", op["externalDocs"])
	}
}

// ---------------------------------------------------------------------------
// TestWebMethodsFixExternalDocs_InComponents — nested Schema externalDocs
// (components.schemas.Pet.externalDocs and deep-nested
// components.schemas.Pet.properties.owner.externalDocs) must both wrap.
// ---------------------------------------------------------------------------
func TestWebMethodsFixExternalDocs_InComponents(t *testing.T) {
	in := []byte(`{"openapi":"3.0.3","info":{"title":"t","version":"1"},"paths":{},"components":{"schemas":{"Pet":{"type":"object","externalDocs":{"url":"https://pet-doc"},"properties":{"owner":{"type":"object","externalDocs":{"url":"https://owner-doc"}}}}}}}`)
	out := fixExternalDocs(in)
	m := unmarshalTo(t, out)

	pet := m["components"].(map[string]interface{})["schemas"].(map[string]interface{})["Pet"].(map[string]interface{})
	if !isArrayOfOneObject(pet["externalDocs"]) {
		t.Errorf("Pet.externalDocs not wrapped: %v", pet["externalDocs"])
	}
	owner := pet["properties"].(map[string]interface{})["owner"].(map[string]interface{})
	if !isArrayOfOneObject(owner["externalDocs"]) {
		t.Errorf("Pet.properties.owner.externalDocs not wrapped: %v", owner["externalDocs"])
	}
}

// ---------------------------------------------------------------------------
// TestWebMethodsFixExternalDocs_DeepNesting — combination: root + tags +
// operation + components.schemas. A single call wraps all sites.
// ---------------------------------------------------------------------------
func TestWebMethodsFixExternalDocs_DeepNesting(t *testing.T) {
	in := []byte(`{
		"openapi":"3.0.3",
		"info":{"title":"t","version":"1"},
		"externalDocs":{"url":"https://root"},
		"tags":[{"name":"pets","externalDocs":{"url":"https://pets"}}],
		"paths":{"/p":{"get":{"externalDocs":{"url":"https://op"},"responses":{}}}},
		"components":{"schemas":{"Pet":{"type":"object","externalDocs":{"url":"https://pet-doc"}}}}
	}`)
	out := fixExternalDocs(in)
	m := unmarshalTo(t, out)

	if !isArrayOfOneObject(m["externalDocs"]) {
		t.Errorf("root externalDocs not wrapped: %v", m["externalDocs"])
	}
	tag0 := m["tags"].([]interface{})[0].(map[string]interface{})
	if !isArrayOfOneObject(tag0["externalDocs"]) {
		t.Errorf("tag[0].externalDocs not wrapped: %v", tag0["externalDocs"])
	}
	op := m["paths"].(map[string]interface{})["/p"].(map[string]interface{})["get"].(map[string]interface{})
	if !isArrayOfOneObject(op["externalDocs"]) {
		t.Errorf("operation externalDocs not wrapped: %v", op["externalDocs"])
	}
	pet := m["components"].(map[string]interface{})["schemas"].(map[string]interface{})["Pet"].(map[string]interface{})
	if !isArrayOfOneObject(pet["externalDocs"]) {
		t.Errorf("Pet.externalDocs not wrapped: %v", pet["externalDocs"])
	}
}

// ---------------------------------------------------------------------------
// TestWebMethodsFixExternalDocs_NoExternalDocs — spec without any
// externalDocs is returned byte-for-byte unchanged (no Unmarshal-Marshal
// round-trip cost, no key-order reshuffle).
// ---------------------------------------------------------------------------
func TestWebMethodsFixExternalDocs_NoExternalDocs(t *testing.T) {
	in := []byte(`{"openapi":"3.0.3","info":{"title":"t","version":"1"},"paths":{"/p":{"get":{"responses":{}}}}}`)
	out := fixExternalDocs(in)
	if !reflect.DeepEqual(in, out) {
		t.Errorf("expected identical bytes when no externalDocs present\nin : %s\nout: %s", string(in), string(out))
	}
}

// ---------------------------------------------------------------------------
// TestWebMethodsFixExternalDocs_AlreadyArray — an externalDocs that is
// already a single-element array must NOT be double-wrapped.
// ---------------------------------------------------------------------------
func TestWebMethodsFixExternalDocs_AlreadyArray(t *testing.T) {
	in := []byte(`{"openapi":"3.0.3","info":{"title":"t","version":"1"},"externalDocs":[{"url":"https://already"}]}`)
	out := fixExternalDocs(in)
	m := unmarshalTo(t, out)

	arr, ok := m["externalDocs"].([]interface{})
	if !ok || len(arr) != 1 {
		t.Fatalf("expected 1-element array, got %v", m["externalDocs"])
	}
	// The element is the original object, not another array.
	if _, isArr := arr[0].([]interface{}); isArr {
		t.Errorf("double-wrap detected: externalDocs[0] is an array, want object")
	}
}

// ---------------------------------------------------------------------------
// TestWebMethodsFixExternalDocs_InvalidJSON — malformed input is returned
// byte-for-byte unchanged (defensive fallback, identical to pre-GO-1 intent).
// ---------------------------------------------------------------------------
func TestWebMethodsFixExternalDocs_InvalidJSON(t *testing.T) {
	in := []byte(`{"openapi":"3.0.3"`) // truncated
	out := fixExternalDocs(in)
	if !reflect.DeepEqual(in, out) {
		t.Errorf("expected identical bytes on parse error\nin : %s\nout: %s", string(in), string(out))
	}
}
