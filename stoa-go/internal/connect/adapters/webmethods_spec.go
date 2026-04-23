package adapters

import (
	"bytes"
	"encoding/json"
	"regexp"
	"strings"
)

// wmNameRe captures characters that webMethods rejects in apiName.
// webMethods only accepts alphanumeric, hyphens, underscores, and dots.
var wmNameRe = regexp.MustCompile(`[^a-zA-Z0-9._-]`)

// sanitizeWMName normalizes an API name to characters webMethods accepts.
func sanitizeWMName(name string) string {
	return wmNameRe.ReplaceAllString(name, "-")
}

// safeMarshal re-encodes parsed JSON and returns the bytes only when they
// round-trip to valid JSON. Any failure (marshal error, invalid bytes) falls
// back to the original spec. Closes GO-1 H.5 — previously each transform
// silently returned its own Marshal output even if malformed, leaving a
// potentially corrupt payload to be sent to webMethods as-is.
func safeMarshal(orig []byte, parsed interface{}) []byte {
	fixed, err := json.Marshal(parsed)
	if err != nil {
		return orig
	}
	if !json.Valid(fixed) {
		return orig
	}
	return fixed
}

// downgradeOpenAPI31 rewrites an OpenAPI 3.1.x spec to 3.0.3.
// webMethods only accepts OpenAPI 3.0.x.
//
// Closes GO-1 L.2 — the previous implementation used a regexp scan on the
// raw bytes, which could false-match any string value that happened to
// contain `"openapi": "3.1.x"` (example metadata, docs strings). Now the
// version is read from the decoded `openapi` top-level field only.
func downgradeOpenAPI31(spec []byte) []byte {
	var parsed map[string]interface{}
	if err := json.Unmarshal(spec, &parsed); err != nil {
		return spec
	}
	v, ok := parsed["openapi"].(string)
	if !ok || !strings.HasPrefix(v, "3.1.") {
		return spec
	}
	parsed["openapi"] = "3.0.3"
	return safeMarshal(spec, parsed)
}

// wrapExternalDocs recursively walks any JSON value and wraps every
// externalDocs single-object occurrence into a single-element array.
// Returns true if any wrap was performed.
//
// The recursion enters each map value and each array item, so nested
// occurrences at arbitrary depth (tags[], paths[].<operation>,
// components.schemas.<name>, Schema.properties.<field>, Schema.items,
// Schema.{allOf|oneOf|anyOf}[*], even inside vendor extensions) are all
// reached in one pass. Values that are already arrays, primitives, or null
// are left untouched.
func wrapExternalDocs(v interface{}) bool {
	modified := false
	switch val := v.(type) {
	case map[string]interface{}:
		if ed, ok := val["externalDocs"]; ok {
			if obj, isObj := ed.(map[string]interface{}); isObj {
				val["externalDocs"] = []interface{}{obj}
				modified = true
			}
		}
		for _, child := range val {
			if wrapExternalDocs(child) {
				modified = true
			}
		}
	case []interface{}:
		for _, item := range val {
			if wrapExternalDocs(item) {
				modified = true
			}
		}
	}
	return modified
}

// fixExternalDocs walks the full OpenAPI document and wraps every
// externalDocs single-object occurrence into a single-element array.
// webMethods expects externalDocs as an array at every level (root, tags[*],
// paths[*].<operation>, components.schemas.<name>, nested Schemas via
// allOf/oneOf/anyOf/items/properties.*/additionalProperties). OpenAPI and
// Swagger specs default to a single object, which webMethods rejects with a
// deserialization error on PUT.
//
// Closes GO-1 H.2 (BUG-REPORT-GO-1.md) — the previous implementation only
// handled the root-level occurrence, letting FastAPI / Swaggerhub specs that
// put externalDocs in tags[] or operations bubble up 500s on PUT.
//
// Malformed input (invalid JSON) is returned unchanged — defensive fallback.
// If the walk produced no modification, the original bytes are returned to
// preserve key ordering.
func fixExternalDocs(spec []byte) []byte {
	var parsed interface{}
	if err := json.Unmarshal(spec, &parsed); err != nil {
		return spec
	}
	if !wrapExternalDocs(parsed) {
		return spec
	}
	return safeMarshal(spec, parsed)
}

// fixSecuritySchemeTypes uppercases securityScheme enum values.
// webMethods expects OAUTH2/HTTP/APIKEY/OPENIDCONNECT, HEADER/QUERY/COOKIE,
// and BASIC/BEARER/DIGEST for http schemes — OpenAPI specs use lowercase
// (oauth2, http, apiKey, header, query, bearer, basic).
//
// GO-1 M.2: the `scheme` field (for type=http) is now uppercased too. Without
// it, `{"type":"http","scheme":"bearer"}` became `{"type":"HTTP","scheme":"bearer"}`
// which webMethods partially rejects.
func fixSecuritySchemeTypes(spec []byte) []byte {
	var parsed map[string]interface{}
	if err := json.Unmarshal(spec, &parsed); err != nil {
		return spec
	}

	components, ok := parsed["components"].(map[string]interface{})
	if !ok {
		return spec
	}
	schemes, ok := components["securitySchemes"].(map[string]interface{})
	if !ok {
		return spec
	}

	modified := false
	for name, v := range schemes {
		scheme, ok := v.(map[string]interface{})
		if !ok {
			continue
		}
		// "scheme" added in GO-1 M.2 (http bearerFormat / basic).
		for _, field := range []string{"type", "in", "scheme"} {
			if val, ok := scheme[field].(string); ok {
				upper := strings.ToUpper(val)
				if upper != val {
					scheme[field] = upper
					modified = true
				}
			}
		}
		schemes[name] = scheme
	}

	if !modified {
		return spec
	}
	return safeMarshal(spec, parsed)
}

// stripResponseSchemas removes schema bodies from response objects in both
// Swagger 2.0 and OpenAPI 3.x specs. webMethods 10.15 RefProperty parser
// crashes on $ref inside response schema objects (and on other complex
// schema constructs). Response schemas aren't needed for gateway routing,
// so we delete them wholesale.
//
// Covered sites:
//   - Swagger 2.0: paths[*].<method>.responses.<code>.schema
//   - OpenAPI 3.x: paths[*].<method>.responses.<code>.content.<mime>.schema
//
// Closes GO-1 H.3 — the pre-fix function (stripSwagger2ResponseRefs) only
// covered the 2.0 shape, so a 3.x spec with $ref in response content still
// crashed webMethods with the same pattern. Renamed to reflect the wider
// scope.
func stripResponseSchemas(spec []byte) []byte {
	// Cheap gate: skip if neither openapi nor swagger marker is present.
	if !bytes.Contains(spec, []byte(`"openapi"`)) && !bytes.Contains(spec, []byte(`"swagger"`)) {
		return spec
	}

	var parsed map[string]interface{}
	if err := json.Unmarshal(spec, &parsed); err != nil {
		return spec
	}

	paths, ok := parsed["paths"].(map[string]interface{})
	if !ok {
		return spec
	}

	modified := false
	for _, pathItem := range paths {
		pi, ok := pathItem.(map[string]interface{})
		if !ok {
			continue
		}
		for _, method := range []string{"get", "post", "put", "delete", "patch", "options", "head"} {
			op, ok := pi[method].(map[string]interface{})
			if !ok {
				continue
			}
			responses, ok := op["responses"].(map[string]interface{})
			if !ok {
				continue
			}
			for code, resp := range responses {
				r, ok := resp.(map[string]interface{})
				if !ok {
					continue
				}
				// Swagger 2.0 shape.
				if _, hasSchema := r["schema"]; hasSchema {
					delete(r, "schema")
					modified = true
				}
				// OpenAPI 3.x shape.
				if content, ok := r["content"].(map[string]interface{}); ok {
					for mime, mediaType := range content {
						mt, ok := mediaType.(map[string]interface{})
						if !ok {
							continue
						}
						if _, hasSchema := mt["schema"]; hasSchema {
							delete(mt, "schema")
							content[mime] = mt
							modified = true
						}
					}
				}
				responses[code] = r
			}
		}
	}

	if !modified {
		return spec
	}
	return safeMarshal(spec, parsed)
}
