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
	client      *http.Client
	cfg         AdapterConfig
	syncedHashes map[string]string // tracks last-synced SpecHash per route name
}

// NewWebMethodsAdapter creates a new webMethods adapter.
func NewWebMethodsAdapter(cfg AdapterConfig) *WebMethodsAdapter {
	return &WebMethodsAdapter{
		client:       &http.Client{Timeout: 10 * time.Second},
		cfg:          cfg,
		syncedHashes: make(map[string]string),
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
// Idempotent: checks if API exists by name, uses PUT to update if so, POST only for new APIs.
// Skips unchanged routes based on SpecHash reconciliation.
func (w *WebMethodsAdapter) SyncRoutes(ctx context.Context, adminURL string, routes []Route) error {
	// Build index of existing APIs by name → ID (single HTTP call)
	existingAPIs, err := w.listAPIsIndexedByName(ctx, adminURL)
	if err != nil {
		return fmt.Errorf("list existing apis: %w", err)
	}

	for _, route := range routes {
		if !route.Activated {
			continue
		}

		wmName := "stoa-" + route.Name

		// SpecHash reconciliation: skip if unchanged since last sync
		if route.SpecHash != "" {
			if lastHash, ok := w.syncedHashes[wmName]; ok && lastHash == route.SpecHash {
				continue
			}
		}

		apiPayload := map[string]interface{}{
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

		data, err := json.Marshal(apiPayload)
		if err != nil {
			return fmt.Errorf("marshal webmethods api: %w", err)
		}

		var method string
		var apiURL string
		if existingID, exists := existingAPIs[wmName]; exists {
			// Update existing API
			method = http.MethodPut
			apiURL = fmt.Sprintf("%s/rest/apigateway/apis/%s", adminURL, existingID)
		} else {
			// Create new API
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
		_ = resp.Body.Close()

		// 409 Conflict on POST = API already exists, treat as success
		if resp.StatusCode == http.StatusConflict {
			continue
		}
		if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
			return fmt.Errorf("webmethods api sync failed (%d)", resp.StatusCode)
		}

		// Track synced hash
		if route.SpecHash != "" {
			w.syncedHashes[wmName] = route.SpecHash
		}
	}

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
