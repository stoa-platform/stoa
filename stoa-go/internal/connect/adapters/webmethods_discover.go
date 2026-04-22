package adapters

import (
	"context"
	"encoding/json"
	"fmt"
)

// Discover lists all APIs from webMethods API Gateway.
// Response shapes: flat `{"apiResponse": [{"apiName": ...}]}` or nested
// `{"apiResponse": [{"api": {...}, "responseStatus": "SUCCESS"}]}`.
// Error/status entries (e.g., `{"responseStatus": "NOT_FOUND"}`) are skipped.
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
