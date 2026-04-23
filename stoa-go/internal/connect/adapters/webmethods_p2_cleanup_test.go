// regression for CAB-1944 (GO-1 audit P2 cleanup, BUG-REPORT-GO-1.md):
// defensive hardening and hygiene across webMethods adapter + cross-adapter
// Detect error propagation. Covers H.3, H.5, M.2, M.3, M.4, L.1, L.2.
package adapters

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// H.5 — json.Valid check after transforms (fail-closed on corruption)
// ---------------------------------------------------------------------------

// TestValidateSpecAfterTransform_InvalidJSON — if a transform's Marshal
// somehow produces invalid JSON (unreachable in practice with
// map[string]interface{}, but defended against), safeMarshal must return
// the original spec unchanged. This guards against future refactors that
// swap the data model or add a custom MarshalJSON that could misbehave.
func TestValidateSpecAfterTransform_InvalidJSON(t *testing.T) {
	orig := []byte(`{"hello":"world"}`)
	// Inject a custom type whose MarshalJSON returns invalid bytes.
	bad := badJSON{}
	out := safeMarshal(orig, bad)
	if string(out) != string(orig) {
		t.Errorf("safeMarshal must fall back to original on invalid JSON, got %q", string(out))
	}
}

type badJSON struct{}

func (badJSON) MarshalJSON() ([]byte, error) { return []byte("not-json"), nil }

// ---------------------------------------------------------------------------
// M.2 — fixSecuritySchemeTypes uppercases `scheme` for http schemes
// ---------------------------------------------------------------------------

// TestFixSecuritySchemeTypes_HTTPScheme — pre-M.2 only `type` and `in` were
// uppercased. For `{"type":"http","scheme":"bearer"}` the output was
// `{"type":"HTTP","scheme":"bearer"}` and webMethods partially rejected.
// Now the `scheme` field also transitions to uppercase.
func TestFixSecuritySchemeTypes_HTTPScheme(t *testing.T) {
	in := []byte(`{"components":{"securitySchemes":{"bearerAuth":{"type":"http","scheme":"bearer"}}}}`)
	out := fixSecuritySchemeTypes(in)

	var m map[string]interface{}
	if err := json.Unmarshal(out, &m); err != nil {
		t.Fatalf("parse: %v", err)
	}
	bearer := m["components"].(map[string]interface{})["securitySchemes"].(map[string]interface{})["bearerAuth"].(map[string]interface{})
	if bearer["type"] != "HTTP" {
		t.Errorf("type: got %v, want HTTP", bearer["type"])
	}
	if bearer["scheme"] != "BEARER" {
		t.Errorf("scheme: got %v, want BEARER (M.2 fix)", bearer["scheme"])
	}
}

// ---------------------------------------------------------------------------
// M.3 — Detect propagates network errors (3 adapters)
// ---------------------------------------------------------------------------

// TestDetect_NetworkErrorPropagated_WebMethods — wM Detect returns the
// underlying HTTP error instead of masking it as (false, nil).
func TestDetect_NetworkErrorPropagated_WebMethods(t *testing.T) {
	adapter := NewWebMethodsAdapter(AdapterConfig{})
	ok, err := adapter.Detect(context.Background(), "http://127.0.0.1:1")
	if err == nil {
		t.Fatal("expected network error")
	}
	if ok {
		t.Error("expected false on unreachable host")
	}
}

// TestDetect_NetworkErrorPropagated_Gravitee — Gravitee Detect mirrors the
// wM fix. Kong is covered in kong_test.go TestKongDetectUnreachable.
func TestDetect_NetworkErrorPropagated_Gravitee(t *testing.T) {
	adapter := NewGraviteeAdapter(AdapterConfig{})
	ok, err := adapter.Detect(context.Background(), "http://127.0.0.1:1")
	if err == nil {
		t.Fatal("expected network error")
	}
	if ok {
		t.Error("expected false on unreachable host")
	}
}

// ---------------------------------------------------------------------------
// M.4 — parseEpochMillis rejects partial parses
// ---------------------------------------------------------------------------

// TestParseEpochMillis_RejectsPartial — pre-M.4 fmt.Sscanf accepted "123abc"
// as 123 with nil error, which silently truncated corrupted timestamps.
// strconv.ParseInt rejects any non-decimal suffix.
func TestParseEpochMillis_RejectsPartial(t *testing.T) {
	if _, err := parseEpochMillis("123abc"); err == nil {
		t.Error("expected error on partial parse, got nil (M.4 not applied?)")
	}
	if got, err := parseEpochMillis("1700000000000"); err != nil || got != 1700000000000 {
		t.Errorf("clean parse: got (%d, %v), want (1700000000000, nil)", got, err)
	}
	if _, err := parseEpochMillis(""); err == nil {
		t.Error("expected error on empty input")
	}
	if _, err := parseEpochMillis("abc"); err == nil {
		t.Error("expected error on non-numeric input")
	}
}

// ---------------------------------------------------------------------------
// L.1 — sanitizeWMName collision warn log
// ---------------------------------------------------------------------------

// TestSyncRoutes_SanitizeCollisionLogged — two route names that collapse
// to the same wM apiName after sanitizeWMName produce a warn log line.
// The sync itself is not blocked — the L.1 scope is "make observable", not
// "harden with errors".
func TestSyncRoutes_SanitizeCollisionLogged(t *testing.T) {
	// Capture log output.
	var buf strings.Builder
	origOutput := log.Writer()
	log.SetOutput(&buf)
	defer log.SetOutput(origOutput)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"apiResponse": []interface{}{}})
		case r.URL.Path == "/rest/apigateway/apis" && r.Method == http.MethodPost:
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "ok"})
		case r.Method == http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"id": "ok", "apiName": "stoa-foo-bar", "isActive": true})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	adapter := NewWebMethodsAdapter(AdapterConfig{})
	// Both names sanitize to "stoa-foo-bar".
	_, _ = adapter.SyncRoutes(context.Background(), server.URL, []Route{
		{Name: "foo/bar", Activated: true},
		{Name: "foo bar", Activated: true},
	})

	out := buf.String()
	if !strings.Contains(out, "collision") {
		t.Errorf("expected collision warn log, got: %s", out)
	}
	if !strings.Contains(out, "stoa-foo-bar") {
		t.Errorf("expected collision log to mention collapsed name, got: %s", out)
	}
}

// ---------------------------------------------------------------------------
// L.2 — openAPI31 detection via JSON parse, not regex
// ---------------------------------------------------------------------------

// TestDowngradeOpenAPI31_ViaJSONParse_NoFalseMatch — a spec whose root
// `openapi` field is 3.0 but whose description contains a literal string
// like `"openapi": "3.1.0"` (in a metadata example) must NOT be downgraded.
// The pre-L.2 regex matched anywhere in the byte stream.
func TestDowngradeOpenAPI31_ViaJSONParse_NoFalseMatch(t *testing.T) {
	// description contains the 3.1.0 pattern as a literal substring.
	in := []byte(`{"openapi":"3.0.0","info":{"title":"t","version":"1","description":"References the openapi 3.1.0 spec for X"}}`)
	out := downgradeOpenAPI31(in)

	var m map[string]interface{}
	if err := json.Unmarshal(out, &m); err != nil {
		t.Fatalf("parse: %v", err)
	}
	if m["openapi"] != "3.0.0" {
		t.Errorf("openapi: got %v, want 3.0.0 (L.2 false-match bug)", m["openapi"])
	}
}

// TestDowngradeOpenAPI31_ViaJSONParse_ActualMatch — baseline: a real 3.1.x
// top-level version IS downgraded.
func TestDowngradeOpenAPI31_ViaJSONParse_ActualMatch(t *testing.T) {
	in := []byte(`{"openapi":"3.1.0","info":{"title":"t","version":"1"}}`)
	out := downgradeOpenAPI31(in)

	var m map[string]interface{}
	if err := json.Unmarshal(out, &m); err != nil {
		t.Fatalf("parse: %v", err)
	}
	if m["openapi"] != "3.0.3" {
		t.Errorf("openapi: got %v, want 3.0.3", m["openapi"])
	}
}

