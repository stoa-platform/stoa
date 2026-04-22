package adapters

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

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

// findPolicyByType searches for an existing policy action by type on a given API.
// Returns the policy ID, or "" if not found.
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

// RemovePolicy removes a policy action from a webMethods API by type.
// Flow: resolve API ID → list policy actions for API → find by type → DELETE.
// Idempotent: returns nil if the policy does not exist.
func (w *WebMethodsAdapter) RemovePolicy(ctx context.Context, adminURL string, apiName string, policyType string) error {
	apiID, err := w.resolveAPIID(ctx, adminURL, apiName)
	if err != nil {
		return err
	}

	wmType, ok := wmPolicyTypeMapping[policyType]
	if !ok {
		wmType = policyType
	}

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

	return nil
}
