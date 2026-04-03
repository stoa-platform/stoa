package adapters

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"regexp"
	"strings"
	"time"
)

// WebMethodsAdapter implements GatewayAdapter for webMethods API Gateway (port 5555).
type WebMethodsAdapter struct {
	client       *http.Client
	cfg          AdapterConfig
	syncedHashes map[string]string            // tracks last-synced SpecHash per route name
	FailedRoutes map[string]string            // deployment_id → error (populated after SyncRoutes)
}

// GetFailedRoutes returns the per-deployment-id error map from the last SyncRoutes call.
func (w *WebMethodsAdapter) GetFailedRoutes() map[string]string {
	return w.FailedRoutes
}

// NewWebMethodsAdapter creates a new webMethods adapter.
func NewWebMethodsAdapter(cfg AdapterConfig) *WebMethodsAdapter {
	return &WebMethodsAdapter{
		client:       &http.Client{Timeout: 10 * time.Second},
		cfg:          cfg,
		syncedHashes: make(map[string]string),
		FailedRoutes: make(map[string]string),
	}
}

// Detect checks if the admin URL hosts a webMethods API Gateway.
func (w *WebMethodsAdapter) Detect(ctx context.Context, adminURL string) (bool, error) {
	url := adminURL + "/rest/apigateway/health"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return false, err
	}
	w.setAuth(req)

	resp, err := w.client.Do(req)
	if err != nil {
		return false, nil
	}
	defer func() { _ = resp.Body.Close() }()

	return resp.StatusCode == http.StatusOK, nil
}

// wmAPI represents an API from webMethods API Gateway.
type wmAPI struct {
	ID             string `json:"id"`
	APIName        string `json:"apiName"`
	APIVersion     string `json:"apiVersion"`
	APIDescription string `json:"apiDescription"`
	IsActive       bool   `json:"isActive"`
	Type           string `json:"type"`
}

// wmAPIWrapper handles the nested response shape: {"api": {...}, "responseStatus": "SUCCESS"}
type wmAPIWrapper struct {
	API            wmAPI  `json:"api"`
	ResponseStatus string `json:"responseStatus"`
}

type wmAPIsResponse struct {
	APIResponse []json.RawMessage `json:"apiResponse"`
}

// wmPolicyAction represents a policy action from webMethods.
type wmPolicyAction struct {
	ID            string `json:"id"`
	TemplateKey   string `json:"templateKey"`
	PolicyName    string `json:"policyActionName"`
}

// Discover lists all APIs from webMethods API Gateway.
func (w *WebMethodsAdapter) Discover(ctx context.Context, adminURL string) ([]DiscoveredAPI, error) {
	apisURL := adminURL + "/rest/apigateway/apis"
	body, err := w.doGet(ctx, apisURL)
	if err != nil {
		return nil, fmt.Errorf("list webmethods apis: %w", err)
	}

	var apisResp wmAPIsResponse
	if err := json.Unmarshal(body, &apisResp); err != nil {
		return nil, fmt.Errorf("decode webmethods apis: %w", err)
	}

	// Parse each API entry — handles both flat and nested shapes:
	//   Flat:   {"apiResponse": [{"apiName": "...", "id": "..."}]}
	//   Nested: {"apiResponse": [{"api": {"apiName": "...", "id": "..."}, "responseStatus": "SUCCESS"}]}
	var parsedAPIs []wmAPI
	for _, raw := range apisResp.APIResponse {
		// Try nested shape first (real webMethods response)
		var wrapper wmAPIWrapper
		if err := json.Unmarshal(raw, &wrapper); err == nil && wrapper.API.APIName != "" {
			parsedAPIs = append(parsedAPIs, wrapper.API)
			continue
		}
		// Try flat shape (test/mock responses)
		var flat wmAPI
		if err := json.Unmarshal(raw, &flat); err == nil && flat.APIName != "" {
			parsedAPIs = append(parsedAPIs, flat)
			continue
		}
		// Skip error/status entries (e.g., {"responseStatus": "NOT_FOUND"})
	}

	var apis []DiscoveredAPI
	for _, wmApi := range parsedAPIs {
		api := DiscoveredAPI{
			Name:     wmApi.APIName,
			Version:  wmApi.APIVersion,
			IsActive: wmApi.IsActive,
		}

		// Get API details for endpoints and policies
		detailURL := fmt.Sprintf("%s/rest/apigateway/apis/%s", adminURL, wmApi.ID)
		detailBody, err := w.doGet(ctx, detailURL)
		if err == nil {
			var detail map[string]interface{}
			if json.Unmarshal(detailBody, &detail) == nil {
				// Extract native endpoint
				if apiResp, ok := detail["apiResponse"].(map[string]interface{}); ok {
					if nativeEndpoint, ok := apiResp["nativeEndpoint"].([]interface{}); ok {
						for _, ep := range nativeEndpoint {
							if epMap, ok := ep.(map[string]interface{}); ok {
								if uri, ok := epMap["uri"].(string); ok {
									api.BackendURL = uri
								}
							}
						}
					}
					// Extract methods from resources
					if resources, ok := apiResp["resources"].([]interface{}); ok {
						for _, r := range resources {
							if rMap, ok := r.(map[string]interface{}); ok {
								if path, ok := rMap["resourcePath"].(string); ok {
									api.Paths = append(api.Paths, path)
								}
								if methods, ok := rMap["methods"].([]interface{}); ok {
									for _, m := range methods {
										if mStr, ok := m.(string); ok {
											api.Methods = append(api.Methods, mStr)
										}
									}
								}
							}
						}
					}
				}
			}
		}

		// Get policies for this API
		policiesURL := fmt.Sprintf("%s/rest/apigateway/apis/%s/policyActions", adminURL, wmApi.ID)
		policiesBody, err := w.doGet(ctx, policiesURL)
		if err == nil {
			var policies struct {
				PolicyActions []wmPolicyAction `json:"policyActions"`
			}
			if json.Unmarshal(policiesBody, &policies) == nil {
				for _, p := range policies.PolicyActions {
					name := p.PolicyName
					if name == "" {
						name = p.TemplateKey
					}
					api.Policies = append(api.Policies, name)
				}
			}
		}

		apis = append(apis, api)
	}

	return apis, nil
}

// wmPolicyTypeMapping maps STOA policy types to webMethods policy action types.
var wmPolicyTypeMapping = map[string]string{
	"cors":       "corsPolicy",
	"rate_limit": "throttlingPolicy",
	"logging":    "logInvocationPolicy",
	"jwt":        "jwtPolicy",
	"ip_filter":  "ipFilterPolicy",
}

// mapPolicyConfig converts STOA-format config to webMethods-specific parameters.
func mapPolicyConfig(wmType string, config map[string]interface{}) map[string]interface{} {
	switch wmType {
	case "corsPolicy":
		return map[string]interface{}{
			"allowedOrigins":   getOrDefault(config, "allowedOrigins", []interface{}{"*"}),
			"allowedMethods":   getOrDefault(config, "allowedMethods", []interface{}{"GET"}),
			"allowedHeaders":   getOrDefault(config, "allowedHeaders", []interface{}{}),
			"exposeHeaders":    getOrDefault(config, "exposeHeaders", []interface{}{}),
			"maxAge":           getOrDefault(config, "maxAge", 3600),
			"allowCredentials": getOrDefault(config, "allowCredentials", false),
		}
	case "throttlingPolicy":
		return map[string]interface{}{
			"maxRequestCount":   getOrDefault(config, "maxRequests", 100),
			"intervalInSeconds": getOrDefault(config, "intervalSeconds", 60),
		}
	case "logInvocationPolicy":
		return map[string]interface{}{
			"logRequestPayload":  getOrDefault(config, "logRequest", true),
			"logResponsePayload": getOrDefault(config, "logResponse", true),
		}
	default:
		return config
	}
}

func getOrDefault(config map[string]interface{}, key string, defaultVal interface{}) interface{} {
	if v, ok := config[key]; ok {
		return v
	}
	return defaultVal
}

// resolveAPIID finds the webMethods API ID by name in a single HTTP call.
func (w *WebMethodsAdapter) resolveAPIID(ctx context.Context, adminURL string, apiName string) (string, error) {
	apisURL := adminURL + "/rest/apigateway/apis"
	body, err := w.doGet(ctx, apisURL)
	if err != nil {
		return "", fmt.Errorf("list apis for resolve: %w", err)
	}

	var apisResp wmAPIsResponse
	if err := json.Unmarshal(body, &apisResp); err != nil {
		return "", fmt.Errorf("decode apis for resolve: %w", err)
	}

	for _, raw := range apisResp.APIResponse {
		var wrapper wmAPIWrapper
		if err := json.Unmarshal(raw, &wrapper); err == nil && wrapper.API.APIName == apiName {
			return wrapper.API.ID, nil
		}
		var flat wmAPI
		if err := json.Unmarshal(raw, &flat); err == nil && flat.APIName == apiName {
			return flat.ID, nil
		}
	}

	return "", fmt.Errorf("webmethods API not found: %s", apiName)
}

// ApplyPolicy upserts a policy action on a webMethods API.
// Flow: resolve API ID → list existing policies → PUT if exists, POST if new.
func (w *WebMethodsAdapter) ApplyPolicy(ctx context.Context, adminURL string, apiName string, policy PolicyAction) error {
	apiID, err := w.resolveAPIID(ctx, adminURL, apiName)
	if err != nil {
		return err
	}

	wmType, ok := wmPolicyTypeMapping[policy.Type]
	if !ok {
		wmType = policy.Type
	}

	// Check for existing policy of this type on the API
	existingID, err := w.findPolicyByType(ctx, adminURL, apiID, wmType, policy.Type)
	if err != nil {
		return fmt.Errorf("find existing policy: %w", err)
	}

	policyAction := map[string]interface{}{
		"policyActionName": fmt.Sprintf("stoa-%s-%s", apiName, policy.Type),
		"type":             wmType,
		"parameters":       mapPolicyConfig(wmType, policy.Config),
	}

	payload := map[string]interface{}{
		"policyAction": policyAction,
		"apiId":        apiID,
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal policy action: %w", err)
	}

	var method, reqURL string
	if existingID != "" {
		method = http.MethodPut
		reqURL = fmt.Sprintf("%s/rest/apigateway/policyActions/%s", adminURL, existingID)
	} else {
		method = http.MethodPost
		reqURL = adminURL + "/rest/apigateway/policyActions"
	}

	req, err := http.NewRequestWithContext(ctx, method, reqURL, bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	w.setAuth(req)

	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("apply webmethods policy: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("webmethods policy apply failed (%d): %s", resp.StatusCode, string(respBody))
	}

	return nil
}

// findPolicyByType searches for an existing policy action by type on a given API.
func (w *WebMethodsAdapter) findPolicyByType(ctx context.Context, adminURL string, apiID string, wmType string, stoaType string) (string, error) {
	policiesURL := fmt.Sprintf("%s/rest/apigateway/apis/%s/policyActions", adminURL, apiID)
	body, err := w.doGet(ctx, policiesURL)
	if err != nil {
		return "", err
	}

	var policies struct {
		PolicyActions []wmPolicyAction `json:"policyActions"`
	}
	if err := json.Unmarshal(body, &policies); err != nil {
		return "", err
	}

	for _, p := range policies.PolicyActions {
		if p.TemplateKey == wmType || p.TemplateKey == stoaType {
			return p.ID, nil
		}
	}
	return "", nil
}

// RemovePolicy removes a policy action from a webMethods API by type.
// Flow: resolve API ID → list policy actions for API → find by type → DELETE
func (w *WebMethodsAdapter) RemovePolicy(ctx context.Context, adminURL string, apiName string, policyType string) error {
	apiID, err := w.resolveAPIID(ctx, adminURL, apiName)
	if err != nil {
		return err
	}

	wmType, ok := wmPolicyTypeMapping[policyType]
	if !ok {
		wmType = policyType
	}

	// List policy actions for this API
	policiesURL := fmt.Sprintf("%s/rest/apigateway/apis/%s/policyActions", adminURL, apiID)
	body, err := w.doGet(ctx, policiesURL)
	if err != nil {
		return fmt.Errorf("list policies for removal: %w", err)
	}

	var policies struct {
		PolicyActions []wmPolicyAction `json:"policyActions"`
	}
	if err := json.Unmarshal(body, &policies); err != nil {
		return fmt.Errorf("decode policy actions: %w", err)
	}

	// Find matching policy by type (templateKey matches wM type)
	for _, p := range policies.PolicyActions {
		if p.TemplateKey == wmType || p.TemplateKey == policyType {
			deleteURL := fmt.Sprintf("%s/rest/apigateway/policyActions/%s", adminURL, p.ID)
			req, err := http.NewRequestWithContext(ctx, http.MethodDelete, deleteURL, nil)
			if err != nil {
				return err
			}
			w.setAuth(req)

			resp, err := w.client.Do(req)
			if err != nil {
				return fmt.Errorf("delete webmethods policy: %w", err)
			}
			_ = resp.Body.Close()

			if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
				return fmt.Errorf("webmethods policy delete failed (%d)", resp.StatusCode)
			}
			return nil
		}
	}

	// Not found = idempotent success
	return nil
}

// ActivateAPI activates a webMethods API by ID.
func (w *WebMethodsAdapter) ActivateAPI(ctx context.Context, adminURL string, apiID string) error {
	reqURL := fmt.Sprintf("%s/rest/apigateway/apis/%s/activate", adminURL, apiID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPut, reqURL, nil)
	if err != nil {
		return err
	}
	w.setAuth(req)

	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("activate webmethods api: %w", err)
	}
	_ = resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		return fmt.Errorf("webmethods api activate failed (%d)", resp.StatusCode)
	}
	return nil
}

// DeactivateAPI deactivates a webMethods API by ID.
func (w *WebMethodsAdapter) DeactivateAPI(ctx context.Context, adminURL string, apiID string) error {
	reqURL := fmt.Sprintf("%s/rest/apigateway/apis/%s/deactivate", adminURL, apiID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPut, reqURL, nil)
	if err != nil {
		return err
	}
	w.setAuth(req)

	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("deactivate webmethods api: %w", err)
	}
	_ = resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		return fmt.Errorf("webmethods api deactivate failed (%d)", resp.StatusCode)
	}
	return nil
}

// DeleteAPI removes an API from webMethods (2-step: deactivate then delete).
// Idempotent: returns nil if the API does not exist.
func (w *WebMethodsAdapter) DeleteAPI(ctx context.Context, adminURL string, apiName string) error {
	apiID, err := w.resolveAPIID(ctx, adminURL, apiName)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			return nil // idempotent
		}
		return err
	}

	// Step 1: deactivate (ignore errors, may already be inactive)
	_ = w.DeactivateAPI(ctx, adminURL, apiID)

	// Step 2: delete
	reqURL := fmt.Sprintf("%s/rest/apigateway/apis/%s", adminURL, apiID)
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, reqURL, nil)
	if err != nil {
		return err
	}
	w.setAuth(req)

	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("delete webmethods api: %w", err)
	}
	_ = resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent && resp.StatusCode != http.StatusNotFound {
		return fmt.Errorf("webmethods api delete failed (%d)", resp.StatusCode)
	}
	return nil
}

// openAPI31Re matches OpenAPI 3.1.x version strings.
var openAPI31Re = regexp.MustCompile(`"openapi"\s*:\s*"3\.1\.\d+"`)

// sanitizeWMName removes characters that webMethods rejects in apiName.
// webMethods only accepts alphanumeric, hyphens, underscores, and dots.
var wmNameRe = regexp.MustCompile(`[^a-zA-Z0-9._-]`)

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

// SyncRoutes pushes CP routes to webMethods via REST API import.
// Idempotent: checks if API exists by name, uses PUT to update if so, POST only for new APIs.
// Deactivated routes are deactivated on the gateway. Skips unchanged routes via SpecHash.
func (w *WebMethodsAdapter) SyncRoutes(ctx context.Context, adminURL string, routes []Route) error {
	existingAPIs, err := w.listAPIsIndexedByName(ctx, adminURL)
	if err != nil {
		return fmt.Errorf("list existing apis: %w", err)
	}

	// Reset per-route failure tracking
	w.FailedRoutes = make(map[string]string)
	var syncErrors []string

	for _, route := range routes {
		wmName := sanitizeWMName("stoa-" + route.Name)

		// Deactivated route: deactivate on gateway if it exists
		if !route.Activated {
			if existingID, exists := existingAPIs[wmName]; exists {
				if err := w.DeactivateAPI(ctx, adminURL, existingID); err != nil {
					return fmt.Errorf("deactivate route %s: %w", route.Name, err)
				}
			}
			continue
		}

		// SpecHash reconciliation: skip if unchanged since last sync
		if route.SpecHash != "" {
			if lastHash, ok := w.syncedHashes[wmName]; ok && lastHash == route.SpecHash {
				continue
			}
		}

		// Fix spec compatibility issues before sending to webMethods
		spec := route.OpenAPISpec
		if len(spec) > 0 {
			spec = downgradeOpenAPI31(spec)
			spec = fixExternalDocs(spec)
			spec = fixSecuritySchemeTypes(spec)
			spec = stripSwagger2ResponseRefs(spec)
		}

		var apiPayload map[string]interface{}
		if len(spec) > 0 {
			// Detect spec type: swagger 2.0 vs openapi 3.x
			specType := "openapi"
			if bytes.Contains(spec, []byte(`"swagger"`)) {
				specType = "swagger"
			}
			// When we have an OpenAPI spec, let wM derive endpoints/resources from it
			apiPayload = map[string]interface{}{
				"apiName":       wmName,
				"apiVersion":    "1.0",
				"type":          specType,
				"apiDefinition": json.RawMessage(spec),
			}
		} else {
			// No spec — build minimal REST API definition manually
			apiPayload = map[string]interface{}{
				"apiName":        wmName,
				"apiVersion":     "1.0",
				"apiDescription": fmt.Sprintf("STOA managed route %s", route.Name),
				"type":           "REST",
				"isActive":       true,
				"nativeEndpoint": []map[string]interface{}{
					{"uri": route.BackendURL},
				},
				"resources": []map[string]interface{}{
					{
						"resourcePath": route.PathPrefix,
						"methods":      route.Methods,
					},
				},
				"tags": []string{"stoa-managed"},
			}
		}

		data, err := json.Marshal(apiPayload)
		if err != nil {
			return fmt.Errorf("marshal webmethods api: %w", err)
		}
		data = fixExternalDocs(data)

		var method string
		var apiURL string
		if existingID, exists := existingAPIs[wmName]; exists {
			method = http.MethodPut
			apiURL = fmt.Sprintf("%s/rest/apigateway/apis/%s", adminURL, existingID)
		} else {
			method = http.MethodPost
			apiURL = adminURL + "/rest/apigateway/apis"
		}

		req, err := http.NewRequestWithContext(ctx, method, apiURL, strings.NewReader(string(data)))
		if err != nil {
			return err
		}
		req.Header.Set("Content-Type", "application/json")
		w.setAuth(req)

		resp, err := w.client.Do(req)
		if err != nil {
			return fmt.Errorf("sync webmethods api: %w", err)
		}
		respBody, _ := io.ReadAll(resp.Body)
		_ = resp.Body.Close()

		if resp.StatusCode == http.StatusConflict {
			continue
		}
		if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
			log.Printf("webmethods: sync %s failed (%d): %s", wmName, resp.StatusCode, string(respBody))
			detail := string(respBody)
			if len(detail) > 300 {
				detail = detail[:300]
			}
			errMsg := fmt.Sprintf("%s: %d — %s", wmName, resp.StatusCode, detail)
			syncErrors = append(syncErrors, errMsg)
			if route.DeploymentID != "" {
				w.FailedRoutes[route.DeploymentID] = fmt.Sprintf("webmethods api sync failed (%d): %s", resp.StatusCode, detail)
			}
			continue
		}

		// Determine API ID for post-deploy verification
		var apiID string
		if existingID, exists := existingAPIs[wmName]; exists {
			apiID = existingID
		} else {
			// Parse response body from POST to extract new API ID
			var createResp struct {
				APIResponse struct {
					API struct {
						ID string `json:"id"`
					} `json:"api"`
				} `json:"apiResponse"`
				ID string `json:"id"`
			}
			if err := json.Unmarshal(respBody, &createResp); err == nil {
				if createResp.APIResponse.API.ID != "" {
					apiID = createResp.APIResponse.API.ID
				} else if createResp.ID != "" {
					apiID = createResp.ID
				}
			}
			if apiID == "" {
				log.Printf("webmethods: could not parse API ID from POST response for %s, skipping activation verify", wmName)
			}
		}

		// Verify the API is actually active on webMethods
		if apiID != "" {
			if err := w.verifyAndActivate(ctx, adminURL, apiID, wmName); err != nil {
				return err
			}
		}

		if route.SpecHash != "" {
			w.syncedHashes[wmName] = route.SpecHash
		}
	}

	if len(syncErrors) > 0 {
		return fmt.Errorf("webmethods api sync failed (%d/%d): %s", len(syncErrors), len(routes), strings.Join(syncErrors, "; "))
	}

	return nil
}

// verifyAndActivate checks that an API is active on webMethods after PUT/POST,
// and activates it if not. Returns error if activation fails.
func (w *WebMethodsAdapter) verifyAndActivate(ctx context.Context, adminURL, apiID, apiName string) error {
	detailURL := fmt.Sprintf("%s/rest/apigateway/apis/%s", adminURL, apiID)
	body, err := w.doGet(ctx, detailURL)
	if err != nil {
		return fmt.Errorf("verify webmethods api %s (%s): %w", apiName, apiID, err)
	}

	// Parse response — try nested shape first, then flat
	var wrapper struct {
		APIResponse wmAPIWrapper `json:"apiResponse"`
	}
	var isActive bool
	if err := json.Unmarshal(body, &wrapper); err == nil && wrapper.APIResponse.API.ID != "" {
		isActive = wrapper.APIResponse.API.IsActive
	} else {
		var flat wmAPI
		if err := json.Unmarshal(body, &flat); err == nil && flat.ID != "" {
			isActive = flat.IsActive
		} else {
			// Cannot determine status — treat as active to avoid false negatives
			return nil
		}
	}

	if isActive {
		log.Printf("webmethods: verifyAndActivate %s (%s): already active", apiName, apiID)
		return nil
	}

	// API is not active — attempt activation
	log.Printf("webmethods: verifyAndActivate %s (%s): isActive=false, activating...", apiName, apiID)
	if err := w.ActivateAPI(ctx, adminURL, apiID); err != nil {
		return fmt.Errorf("API created but activation failed on webMethods: %s (%s): %w", apiName, apiID, err)
	}
	log.Printf("webmethods: verifyAndActivate %s (%s): activated successfully", apiName, apiID)
	return nil
}

// listAPIsIndexedByName returns a map of API name → API ID from a single list call.
func (w *WebMethodsAdapter) listAPIsIndexedByName(ctx context.Context, adminURL string) (map[string]string, error) {
	apisURL := adminURL + "/rest/apigateway/apis"
	body, err := w.doGet(ctx, apisURL)
	if err != nil {
		return nil, err
	}

	var apisResp wmAPIsResponse
	if err := json.Unmarshal(body, &apisResp); err != nil {
		return nil, err
	}

	index := make(map[string]string)
	for _, raw := range apisResp.APIResponse {
		var wrapper wmAPIWrapper
		if err := json.Unmarshal(raw, &wrapper); err == nil && wrapper.API.APIName != "" {
			index[wrapper.API.APIName] = wrapper.API.ID
			continue
		}
		var flat wmAPI
		if err := json.Unmarshal(raw, &flat); err == nil && flat.APIName != "" {
			index[flat.APIName] = flat.ID
			continue
		}
	}

	return index, nil
}

// InjectCredentials provisions applications and API associations on webMethods.
// Two-step process: (1) create application, (2) associate with APIs.
func (w *WebMethodsAdapter) InjectCredentials(ctx context.Context, adminURL string, creds []Credential) error {
	for _, cred := range creds {
		// Step 1: Create application
		appPayload := map[string]interface{}{
			"name":        "stoa-" + cred.ConsumerID,
			"description": fmt.Sprintf("STOA managed consumer %s", cred.ConsumerID),
			"identifiers": []map[string]interface{}{
				{"key": cred.Key, "name": "apiKey", "value": []string{cred.Key}},
			},
		}

		data, err := json.Marshal(appPayload)
		if err != nil {
			return fmt.Errorf("marshal webmethods app: %w", err)
		}

		appURL := adminURL + "/rest/apigateway/applications"
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, appURL, strings.NewReader(string(data)))
		if err != nil {
			return err
		}
		req.Header.Set("Content-Type", "application/json")
		w.setAuth(req)

		resp, err := w.client.Do(req)
		if err != nil {
			return fmt.Errorf("create webmethods application: %w", err)
		}

		// Read response body to extract application ID
		respBody, _ := io.ReadAll(resp.Body)
		_ = resp.Body.Close()

		if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusConflict {
			return fmt.Errorf("webmethods app create failed (%d): %s", resp.StatusCode, string(respBody))
		}

		// Extract application ID from response
		var appResp struct {
			ID string `json:"id"`
		}
		if err := json.Unmarshal(respBody, &appResp); err != nil || appResp.ID == "" {
			// If we can't get the ID (e.g., 409 Conflict), skip association
			continue
		}

		// Step 2: Associate application with APIs
		if cred.APIName != "" {
			apiID, err := w.resolveAPIID(ctx, adminURL, cred.APIName)
			if err != nil {
				return fmt.Errorf("resolve API for credential association: %w", err)
			}

			assocPayload := map[string]interface{}{
				"apiIDs": []string{apiID},
			}
			assocData, err := json.Marshal(assocPayload)
			if err != nil {
				return fmt.Errorf("marshal api association: %w", err)
			}

			assocURL := fmt.Sprintf("%s/rest/apigateway/applications/%s/apis", adminURL, appResp.ID)
			assocReq, err := http.NewRequestWithContext(ctx, http.MethodPost, assocURL, strings.NewReader(string(assocData)))
			if err != nil {
				return err
			}
			assocReq.Header.Set("Content-Type", "application/json")
			w.setAuth(assocReq)

			assocResp, err := w.client.Do(assocReq)
			if err != nil {
				return fmt.Errorf("associate webmethods app with api: %w", err)
			}
			_ = assocResp.Body.Close()

			if assocResp.StatusCode != http.StatusOK && assocResp.StatusCode != http.StatusCreated && assocResp.StatusCode != http.StatusConflict {
				return fmt.Errorf("webmethods app-api association failed (%d)", assocResp.StatusCode)
			}
		}
	}
	return nil
}

// --- OIDC Support (OIDCAdapter interface) ---

// wmAlias represents an alias from webMethods API Gateway.
type wmAlias struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	Type string `json:"type"`
}

type wmAliasListResponse struct {
	Alias []wmAlias `json:"alias"`
}

// wmStrategy represents a strategy from webMethods API Gateway.
type wmStrategy struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

type wmStrategyListResponse struct {
	Strategies []wmStrategy `json:"strategy"`
}

// listAliases fetches all aliases from webMethods.
func (w *WebMethodsAdapter) listAliases(ctx context.Context, adminURL string) ([]wmAlias, error) {
	body, err := w.doGet(ctx, adminURL+"/rest/apigateway/alias")
	if err != nil {
		return nil, fmt.Errorf("list aliases: %w", err)
	}
	var resp wmAliasListResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil, fmt.Errorf("decode aliases: %w", err)
	}
	return resp.Alias, nil
}

// listStrategies fetches all strategies from webMethods.
func (w *WebMethodsAdapter) listStrategies(ctx context.Context, adminURL string) ([]wmStrategy, error) {
	body, err := w.doGet(ctx, adminURL+"/rest/apigateway/strategies")
	if err != nil {
		return nil, fmt.Errorf("list strategies: %w", err)
	}
	var resp wmStrategyListResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil, fmt.Errorf("decode strategies: %w", err)
	}
	return resp.Strategies, nil
}

// UpsertAuthServer creates or updates an OIDC auth server alias on webMethods.
func (w *WebMethodsAdapter) UpsertAuthServer(ctx context.Context, adminURL string, spec AuthServerSpec) error {
	scopes := spec.Scopes
	if len(scopes) == 0 {
		scopes = []string{"openid"}
	}
	payload := map[string]interface{}{
		"name": spec.Name, "description": spec.Description, "type": "authServerAlias",
		"discoveryURL": spec.DiscoveryURL, "introspectionURL": spec.IntrospectionURL,
		"clientId": spec.ClientID, "clientSecret": spec.ClientSecret, "scopes": scopes,
	}
	existing, err := w.listAliases(ctx, adminURL)
	if err != nil {
		return err
	}
	var existingID string
	for _, a := range existing {
		if a.Name == spec.Name && a.Type == "authServerAlias" {
			existingID = a.ID
			break
		}
	}
	return w.upsertResource(ctx, adminURL, "/rest/apigateway/alias", existingID, payload)
}

// DeleteAuthServer removes an auth server alias by name.
func (w *WebMethodsAdapter) DeleteAuthServer(ctx context.Context, adminURL string, name string) error {
	existing, err := w.listAliases(ctx, adminURL)
	if err != nil {
		return err
	}
	for _, a := range existing {
		if a.Name == name && a.Type == "authServerAlias" {
			return w.doDelete(ctx, fmt.Sprintf("%s/rest/apigateway/alias/%s", adminURL, a.ID))
		}
	}
	return nil
}

// UpsertStrategy creates or updates an OAuth2 strategy on webMethods.
func (w *WebMethodsAdapter) UpsertStrategy(ctx context.Context, adminURL string, spec StrategySpec) error {
	strategyType := spec.Type
	if strategyType == "" {
		strategyType = "OAUTH2"
	}
	payload := map[string]interface{}{
		"name": spec.Name, "description": spec.Description, "type": strategyType,
		"authServerAlias": spec.AuthServerAlias, "clientId": spec.ClientID,
		"audience": spec.Audience,
	}
	existing, err := w.listStrategies(ctx, adminURL)
	if err != nil {
		return err
	}
	var existingID string
	for _, s := range existing {
		if s.Name == spec.Name {
			existingID = s.ID
			break
		}
	}
	return w.upsertResource(ctx, adminURL, "/rest/apigateway/strategies", existingID, payload)
}

// UpsertScope creates a scope mapping on webMethods.
func (w *WebMethodsAdapter) UpsertScope(ctx context.Context, adminURL string, spec ScopeSpec) error {
	keycloakScope := spec.KeycloakScope
	if keycloakScope == "" {
		keycloakScope = "openid"
	}
	payload := map[string]interface{}{
		"scopeName": spec.ScopeName, "description": spec.Description,
		"audience": spec.Audience, "apiIds": spec.APIIDs,
		"authServerAlias": spec.AuthServerAlias, "keycloakScope": keycloakScope,
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal scope: %w", err)
	}
	scopeURL := adminURL + "/rest/apigateway/scopes"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, scopeURL, bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	w.setAuth(req)
	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("create scope: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusConflict {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("scope create failed (%d): %s", resp.StatusCode, string(respBody))
	}
	return nil
}

// --- Alias Support (AliasAdapter interface) ---

// UpsertAlias creates or updates an endpoint alias on webMethods.
func (w *WebMethodsAdapter) UpsertAlias(ctx context.Context, adminURL string, spec AliasSpec) error {
	aliasType := spec.Type
	if aliasType == "" {
		aliasType = "endpoint"
	}
	connTimeout := spec.ConnectionTimeout
	if connTimeout == 0 {
		connTimeout = 30
	}
	readTimeout := spec.ReadTimeout
	if readTimeout == 0 {
		readTimeout = 60
	}
	optimization := spec.Optimization
	if optimization == "" {
		optimization = "None"
	}
	payload := map[string]interface{}{
		"name": spec.Name, "description": spec.Description, "type": aliasType,
		"endPointURI": spec.EndpointURI, "connectionTimeout": connTimeout,
		"readTimeout": readTimeout, "optimizationTechnique": optimization,
		"passSecurityHeaders": spec.PassSecurityHeaders,
	}
	existing, err := w.listAliases(ctx, adminURL)
	if err != nil {
		return err
	}
	var existingID string
	for _, a := range existing {
		if a.Name == spec.Name && a.Type != "authServerAlias" {
			existingID = a.ID
			break
		}
	}
	return w.upsertResource(ctx, adminURL, "/rest/apigateway/alias", existingID, payload)
}

// DeleteAlias removes an alias by name.
func (w *WebMethodsAdapter) DeleteAlias(ctx context.Context, adminURL string, name string) error {
	existing, err := w.listAliases(ctx, adminURL)
	if err != nil {
		return err
	}
	for _, a := range existing {
		if a.Name == name {
			return w.doDelete(ctx, fmt.Sprintf("%s/rest/apigateway/alias/%s", adminURL, a.ID))
		}
	}
	return nil
}

// --- Shared helpers ---

func (w *WebMethodsAdapter) upsertResource(ctx context.Context, adminURL string, basePath string, existingID string, payload map[string]interface{}) error {
	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal resource: %w", err)
	}
	var method, resourceURL string
	if existingID != "" {
		method = http.MethodPut
		resourceURL = fmt.Sprintf("%s%s/%s", adminURL, basePath, existingID)
	} else {
		method = http.MethodPost
		resourceURL = adminURL + basePath
	}
	req, err := http.NewRequestWithContext(ctx, method, resourceURL, bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	w.setAuth(req)
	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("upsert resource: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusConflict {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("upsert failed (%d): %s", resp.StatusCode, string(respBody))
	}
	return nil
}

func (w *WebMethodsAdapter) doDelete(ctx context.Context, deleteURL string) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, deleteURL, nil)
	if err != nil {
		return err
	}
	w.setAuth(req)
	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("delete resource: %w", err)
	}
	_ = resp.Body.Close()
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent && resp.StatusCode != http.StatusNotFound {
		return fmt.Errorf("delete failed (%d)", resp.StatusCode)
	}
	return nil
}
func (w *WebMethodsAdapter) doGet(ctx context.Context, url string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	w.setAuth(req)
	req.Header.Set("Accept", "application/json")

	resp, err := w.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("GET %s returned %d: %s", url, resp.StatusCode, string(body))
	}

	return io.ReadAll(resp.Body)
}

func (w *WebMethodsAdapter) setAuth(req *http.Request) {
	if w.cfg.Username != "" {
		req.SetBasicAuth(w.cfg.Username, w.cfg.Password)
	}
}

// --- Telemetry Collection ---

// wmTransactionalEvent represents a raw transactional event from webMethods.
type wmTransactionalEvent struct {
	EventTimestamp string `json:"eventTimestamp"` // epoch millis as string
	APIID          string `json:"apiId"`
	APIName        string `json:"apiName"`
	OperationName  string `json:"operationName"`
	HTTPMethod     string `json:"httpMethod"`
	ResourcePath   string `json:"resourcePath"`
	Status         int    `json:"status"`
	TotalTime      int64  `json:"totalTime"` // milliseconds
	TenantID       string `json:"tenantId"`
}

// NormalizeEvent converts a raw webMethods transactional event to the common schema.
func NormalizeEvent(raw wmTransactionalEvent) TelemetryEvent {
	var ts time.Time
	if raw.EventTimestamp != "" {
		if ms, err := parseEpochMillis(raw.EventTimestamp); err == nil {
			ts = time.UnixMilli(ms)
		}
	}
	if ts.IsZero() {
		ts = time.Now().UTC()
	}

	method := raw.HTTPMethod
	if method == "" {
		method = raw.OperationName
	}

	return TelemetryEvent{
		Timestamp: ts,
		Method:    method,
		Path:      raw.ResourcePath,
		Status:    raw.Status,
		LatencyMs: raw.TotalTime,
		TenantID:  raw.TenantID,
		APIName:   raw.APIName,
		APIID:     raw.APIID,
	}
}

// parseEpochMillis parses a string epoch timestamp in milliseconds.
func parseEpochMillis(s string) (int64, error) {
	var ms int64
	_, err := fmt.Sscanf(s, "%d", &ms)
	return ms, err
}

// SubscribeTelemetry creates a push subscription on webMethods to receive transactional events.
// callbackURL is the URL where webMethods will POST events (e.g., http://stoa-connect:8090/webhook/events).
// Returns the subscription ID. Trial license resets lose subscriptions — recreate on agent restart.
func (w *WebMethodsAdapter) SubscribeTelemetry(ctx context.Context, adminURL string, callbackURL string) (string, error) {
	payload := map[string]interface{}{
		"eventType":   "transactionalEvents",
		"callbackURL": callbackURL,
		"active":      true,
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("marshal subscription: %w", err)
	}

	subURL := adminURL + "/rest/apigateway/subscriptions"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, subURL, bytes.NewReader(data))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	w.setAuth(req)

	resp, err := w.client.Do(req)
	if err != nil {
		return "", fmt.Errorf("create telemetry subscription: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("subscription create failed (%d): %s", resp.StatusCode, string(respBody))
	}

	var result struct {
		ID string `json:"id"`
	}
	if err := json.Unmarshal(respBody, &result); err != nil {
		return "", fmt.Errorf("decode subscription response: %w", err)
	}

	return result.ID, nil
}

// PollTelemetry fetches transactional events from webMethods for the given time range.
// fromDate and toDate are epoch milliseconds. Used as fallback when push subscription fails.
func (w *WebMethodsAdapter) PollTelemetry(ctx context.Context, adminURL string, fromDate, toDate int64) ([]TelemetryEvent, error) {
	pollURL := fmt.Sprintf("%s/rest/apigateway/transactionalEvents?fromDate=%d&toDate=%d&size=100",
		adminURL, fromDate, toDate)

	body, err := w.doGet(ctx, pollURL)
	if err != nil {
		return nil, fmt.Errorf("poll telemetry events: %w", err)
	}

	var resp struct {
		TransactionalEvents []wmTransactionalEvent `json:"transactionalEvents"`
	}
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil, fmt.Errorf("decode telemetry events: %w", err)
	}

	events := make([]TelemetryEvent, 0, len(resp.TransactionalEvents))
	for _, raw := range resp.TransactionalEvents {
		events = append(events, NormalizeEvent(raw))
	}

	return events, nil
}

// --- Gateway Configuration ---

// ApplyConfig updates a webMethods gateway configuration by key.
// Supported keys: errorProcessing, jwt, keystore.
func (w *WebMethodsAdapter) ApplyConfig(ctx context.Context, adminURL string, configKey string, config map[string]interface{}) error {
	data, err := json.Marshal(config)
	if err != nil {
		return fmt.Errorf("marshal config: %w", err)
	}

	cfgURL := fmt.Sprintf("%s/rest/apigateway/configurations/%s", adminURL, configKey)
	req, err := http.NewRequestWithContext(ctx, http.MethodPut, cfgURL, bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	w.setAuth(req)

	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("apply webmethods config: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("config update failed (%d): %s", resp.StatusCode, string(respBody))
	}

	return nil
}

// HandleWebhookEvents parses a batch of webMethods push events from a webhook POST body.
func HandleWebhookEvents(body []byte) ([]TelemetryEvent, error) {
	var payload struct {
		Events []wmTransactionalEvent `json:"events"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, fmt.Errorf("decode webhook events: %w", err)
	}

	events := make([]TelemetryEvent, 0, len(payload.Events))
	for _, raw := range payload.Events {
		events = append(events, NormalizeEvent(raw))
	}

	return events, nil
}
