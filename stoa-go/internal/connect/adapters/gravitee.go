package adapters

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// GraviteeAdapter implements GatewayAdapter for Gravitee APIM (port 8083).
type GraviteeAdapter struct {
	client *http.Client
	cfg    AdapterConfig
}

// NewGraviteeAdapter creates a new Gravitee adapter.
func NewGraviteeAdapter(cfg AdapterConfig) *GraviteeAdapter {
	return &GraviteeAdapter{
		client: &http.Client{Timeout: 10 * time.Second},
		cfg:    cfg,
	}
}

// Detect checks if the admin URL hosts a Gravitee Management API.
func (g *GraviteeAdapter) Detect(ctx context.Context, adminURL string) (bool, error) {
	url := adminURL + "/management/v2/organizations/DEFAULT"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return false, err
	}
	g.setAuth(req)

	resp, err := g.client.Do(req)
	if err != nil {
		return false, nil
	}
	defer resp.Body.Close()

	return resp.StatusCode == http.StatusOK, nil
}

// graviteeAPI represents an API from Gravitee's Management API v2.
type graviteeAPI struct {
	ID                string `json:"id"`
	Name              string `json:"name"`
	APIVersion        string `json:"apiVersion"`
	State             string `json:"state"`
	DefinitionVersion string `json:"definitionVersion"`
}

type graviteeAPIsResponse struct {
	Data []graviteeAPI `json:"data"`
}

// graviteePlan represents a plan associated with a Gravitee API.
type graviteePlan struct {
	Name   string          `json:"name"`
	Status string          `json:"status"`
	Flows  []graviteeFlow  `json:"flows"`
}

type graviteeFlow struct {
	Pre []graviteePolicy `json:"pre"`
}

type graviteePolicy struct {
	Policy string `json:"policy"`
}

// graviteePlansResponse from Gravitee API.
type graviteePlansResponse struct {
	Data []graviteePlan `json:"data"`
}

// Discover lists all APIs from Gravitee's Management API.
func (g *GraviteeAdapter) Discover(ctx context.Context, adminURL string) ([]DiscoveredAPI, error) {
	apisURL := adminURL + "/management/v2/environments/DEFAULT/apis"
	body, err := g.doGet(ctx, apisURL)
	if err != nil {
		return nil, fmt.Errorf("list gravitee apis: %w", err)
	}

	var apisResp graviteeAPIsResponse
	if err := json.Unmarshal(body, &apisResp); err != nil {
		return nil, fmt.Errorf("decode gravitee apis: %w", err)
	}

	var apis []DiscoveredAPI
	for _, gAPI := range apisResp.Data {
		api := DiscoveredAPI{
			Name:     gAPI.Name,
			Version:  gAPI.APIVersion,
			IsActive: gAPI.State == "STARTED",
		}

		// Get API details for paths and backend
		detailURL := fmt.Sprintf("%s/management/v2/environments/DEFAULT/apis/%s", adminURL, gAPI.ID)
		detailBody, err := g.doGet(ctx, detailURL)
		if err == nil {
			var detail map[string]interface{}
			if json.Unmarshal(detailBody, &detail) == nil {
				// Extract paths from listeners
				if listeners, ok := detail["listeners"].([]interface{}); ok {
					for _, l := range listeners {
						if lMap, ok := l.(map[string]interface{}); ok {
							if paths, ok := lMap["paths"].([]interface{}); ok {
								for _, p := range paths {
									if pMap, ok := p.(map[string]interface{}); ok {
										if path, ok := pMap["path"].(string); ok {
											api.Paths = append(api.Paths, path)
										}
									}
								}
							}
						}
					}
				}

				// Extract backend URL from endpoint groups
				if groups, ok := detail["endpointGroups"].([]interface{}); ok {
					for _, grp := range groups {
						if grpMap, ok := grp.(map[string]interface{}); ok {
							if endpoints, ok := grpMap["endpoints"].([]interface{}); ok {
								for _, ep := range endpoints {
									if epMap, ok := ep.(map[string]interface{}); ok {
										if target, ok := epMap["target"].(string); ok {
											api.BackendURL = target
										}
									}
								}
							}
						}
					}
				}
			}
		}

		// Get plans for policies
		plansURL := fmt.Sprintf("%s/management/v2/environments/DEFAULT/apis/%s/plans", adminURL, gAPI.ID)
		plansBody, err := g.doGet(ctx, plansURL)
		if err == nil {
			var plans graviteePlansResponse
			if json.Unmarshal(plansBody, &plans) == nil {
				for _, plan := range plans.Data {
					for _, flow := range plan.Flows {
						for _, pre := range flow.Pre {
							api.Policies = append(api.Policies, pre.Policy)
						}
					}
				}
			}
		}

		apis = append(apis, api)
	}

	return apis, nil
}

// ApplyPolicy creates or updates a plan with the given policy on a Gravitee API.
func (g *GraviteeAdapter) ApplyPolicy(ctx context.Context, adminURL string, apiName string, policy PolicyAction) error {
	// For Gravitee, policies are applied via Plans with flows
	return fmt.Errorf("gravitee policy sync not yet implemented")
}

// RemovePolicy removes a policy from a Gravitee API's plans.
func (g *GraviteeAdapter) RemovePolicy(ctx context.Context, adminURL string, apiName string, policyType string) error {
	return fmt.Errorf("gravitee policy sync not yet implemented")
}

func (g *GraviteeAdapter) doGet(ctx context.Context, url string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	g.setAuth(req)

	resp, err := g.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("GET %s returned %d: %s", url, resp.StatusCode, string(body))
	}

	return io.ReadAll(resp.Body)
}

func (g *GraviteeAdapter) setAuth(req *http.Request) {
	if g.cfg.Username != "" {
		req.SetBasicAuth(g.cfg.Username, g.cfg.Password)
	}
}
