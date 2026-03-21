package adapters

import (
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

type wmAPIsResponse struct {
	APIResponse []wmAPI `json:"apiResponse"`
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
		// webMethods may return different shapes — try array
		var apiList []wmAPI
		if err2 := json.Unmarshal(body, &apiList); err2 != nil {
			return nil, fmt.Errorf("decode webmethods apis: %w", err)
		}
		apisResp.APIResponse = apiList
	}

	var apis []DiscoveredAPI
	for _, wmApi := range apisResp.APIResponse {
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

// ApplyPolicy pushes a policy action to a webMethods API.
func (w *WebMethodsAdapter) ApplyPolicy(ctx context.Context, adminURL string, apiName string, policy PolicyAction) error {
	return fmt.Errorf("webmethods policy sync not yet implemented")
}

// RemovePolicy removes a policy action from a webMethods API.
func (w *WebMethodsAdapter) RemovePolicy(ctx context.Context, adminURL string, apiName string, policyType string) error {
	return fmt.Errorf("webmethods policy sync not yet implemented")
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
