package adapters

import (
	"bytes"
	"encoding/json"
	"regexp"
	"strings"
)

// openAPI31Re matches OpenAPI 3.1.x version strings.
var openAPI31Re = regexp.MustCompile(`"openapi"\s*:\s*"3\.1\.\d+"`)

// wmNameRe captures characters that webMethods rejects in apiName.
// webMethods only accepts alphanumeric, hyphens, underscores, and dots.
var wmNameRe = regexp.MustCompile(`[^a-zA-Z0-9._-]`)

// sanitizeWMName normalizes an API name to characters webMethods accepts.
func sanitizeWMName(name string) string {
	return wmNameRe.ReplaceAllString(name, "-")
}

// downgradeOpenAPI31 rewrites an OpenAPI 3.1.x spec to 3.0.3.
// webMethods only accepts OpenAPI 3.0.x.
func downgradeOpenAPI31(spec []byte) []byte {
	if !openAPI31Re.Match(spec) {
		return spec
	}
	return openAPI31Re.ReplaceAll(spec, []byte(`"openapi": "3.0.3"`))
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
	fixed, err := json.Marshal(parsed)
	if err != nil {
		return spec
	}
	return fixed
}

// fixSecuritySchemeTypes uppercases securityScheme enum values.
// webMethods expects OAUTH2/HTTP/APIKEY/OPENIDCONNECT and HEADER/QUERY/COOKIE,
// but OpenAPI specs use lowercase: oauth2, http, apiKey, header, query.
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
		for _, field := range []string{"type", "in"} {
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

	fixed, err := json.Marshal(parsed)
	if err != nil {
		return spec
	}
	return fixed
}

// stripSwagger2ResponseRefs removes $ref from response schemas in Swagger 2.0 specs.
// webMethods 10.15 RefProperty parser crashes on $ref inside response schema objects
// (e.g. {"schema":{"$ref":"#/definitions/Pet"}}). We strip the schema entirely since
// webMethods doesn't use response schemas for routing — it only needs paths + methods.
func stripSwagger2ResponseRefs(spec []byte) []byte {
	if !bytes.Contains(spec, []byte(`"swagger"`)) {
		return spec // Not Swagger 2.0
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
				// Strip ALL response schemas — webMethods RefProperty parser
				// crashes on $ref, additionalProperties, and other complex
				// schema constructs during PUT. Response schemas aren't needed
				// for gateway routing.
				if _, hasSchema := r["schema"]; hasSchema {
					delete(r, "schema")
					responses[code] = r
					modified = true
				}
			}
		}
	}

	if !modified {
		return spec
	}

	fixed, err := json.Marshal(parsed)
	if err != nil {
		return spec
	}
	return fixed
}
