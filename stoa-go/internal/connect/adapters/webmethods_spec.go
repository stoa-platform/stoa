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

// fixExternalDocs wraps externalDocs object into an array if needed.
// webMethods expects externalDocs as an array, but OpenAPI/Swagger specs
// define it as a single object. This causes deserialization errors on PUT.
func fixExternalDocs(spec []byte) []byte {
	var parsed map[string]interface{}
	if err := json.Unmarshal(spec, &parsed); err != nil {
		return spec
	}

	ed, ok := parsed["externalDocs"]
	if !ok {
		return spec
	}

	// If it's already an array, no fix needed
	if _, isArray := ed.([]interface{}); isArray {
		return spec
	}

	// If it's an object, wrap in array
	if obj, isObj := ed.(map[string]interface{}); isObj {
		parsed["externalDocs"] = []interface{}{obj}
		fixed, err := json.Marshal(parsed)
		if err != nil {
			return spec
		}
		return fixed
	}

	return spec
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
