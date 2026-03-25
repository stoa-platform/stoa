package adapters

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// WebMethodsAdapter implements GatewayAdapter for webMethods API Gateway (port 5555).
type WebMethodsAdapter struct {
	client *http.Client
	cfg    AdapterConfig
}

// NewWebMethodsAdapter creates a new webMethods adapter.
func NewWebMethodsAdapter(cfg AdapterConfig) *WebMethodsAdapter {
	return &WebMethodsAdapter{
		client: &http.Client{Timeout: 10 * time.Second},
		cfg:    cfg,
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

// resolveAPIID finds the webMethods API ID by name.
func (w *WebMethodsAdapter) resolveAPIID(ctx context.Context, adminURL string, apiName string) (string, error) {
	// Use Discover to get parsed APIs (handles both flat and nested response shapes)
	apis, err := w.Discover(ctx, adminURL)
	if err != nil {
		return "", fmt.Errorf("list apis for resolve: %w", err)
	}

	for _, api := range apis {
		if api.Name == apiName {
			// We need the wM ID, not just the name. Re-fetch from raw response.
			break
		}
	}

	// Direct lookup from raw response for the ID
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

	_ = apis // suppress unused warning
	return "", fmt.Errorf("webmethods API not found: %s", apiName)
}

// ApplyPolicy pushes a policy action to a webMethods API.
// Flow: resolve API ID → map type → POST /rest/apigateway/policyActions
func (w *WebMethodsAdapter) ApplyPolicy(ctx context.Context, adminURL string, apiName string, policy PolicyAction) error {
	apiID, err := w.resolveAPIID(ctx, adminURL, apiName)
	if err != nil {
		return err
	}

	wmType, ok := wmPolicyTypeMapping[policy.Type]
	if !ok {
		wmType = policy.Type
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

	url := adminURL + "/rest/apigateway/policyActions"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(data))
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

// SyncRoutes pushes CP routes to webMethods via REST API import.
func (w *WebMethodsAdapter) SyncRoutes(ctx context.Context, adminURL string, routes []Route) error {
	for _, route := range routes {
		if !route.Activated {
			continue
		}

		// Build a minimal API payload for webMethods import
		apiPayload := map[string]interface{}{
			"apiName":        "stoa-" + route.Name,
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

		data, err := json.Marshal(apiPayload)
		if err != nil {
			return fmt.Errorf("marshal webmethods api: %w", err)
		}

		apiURL := adminURL + "/rest/apigateway/apis"
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, apiURL, strings.NewReader(string(data)))
		if err != nil {
			return err
		}
		req.Header.Set("Content-Type", "application/json")
		w.setAuth(req)

		resp, err := w.client.Do(req)
		if err != nil {
			return fmt.Errorf("create webmethods api: %w", err)
		}
		_ = resp.Body.Close()

		if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
			return fmt.Errorf("webmethods api create failed (%d)", resp.StatusCode)
		}
	}

	return nil
}

// InjectCredentials provisions applications and API associations on webMethods.
func (w *WebMethodsAdapter) InjectCredentials(ctx context.Context, adminURL string, creds []Credential) error {
	for _, cred := range creds {
		// 1. Create application
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
		_ = resp.Body.Close()

		if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusConflict {
			return fmt.Errorf("webmethods app create failed (%d)", resp.StatusCode)
		}
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
