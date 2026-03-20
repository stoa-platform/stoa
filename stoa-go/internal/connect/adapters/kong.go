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

// KongAdapter implements GatewayAdapter for Kong (DB-less mode, port 8001).
type KongAdapter struct {
	client *http.Client
	cfg    AdapterConfig
}

// NewKongAdapter creates a new Kong adapter.
func NewKongAdapter(cfg AdapterConfig) *KongAdapter {
	return &KongAdapter{
		client: &http.Client{Timeout: 10 * time.Second},
		cfg:    cfg,
	}
}

// Detect checks if the admin URL hosts a Kong gateway.
// Kong's root endpoint returns {"tagline":"Welcome to kong"}.
func (k *KongAdapter) Detect(ctx context.Context, adminURL string) (bool, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, adminURL+"/", nil)
	if err != nil {
		return false, err
	}
	k.setAuth(req)

	resp, err := k.client.Do(req)
	if err != nil {
		return false, nil // Not reachable = not Kong
	}
	defer func() { _ = resp.Body.Close() }()

	body, _ := io.ReadAll(resp.Body)
	var result map[string]interface{}
	if err := json.Unmarshal(body, &result); err != nil {
		return false, nil
	}

	tagline, _ := result["tagline"].(string)
	return strings.Contains(strings.ToLower(tagline), "kong"), nil
}

// kongService represents a Kong service from the Admin API.
type kongService struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	Host     string `json:"host"`
	Port     int    `json:"port"`
	Protocol string `json:"protocol"`
	Path     string `json:"path"`
	Enabled  bool   `json:"enabled"`
}

type kongServicesResponse struct {
	Data []kongService `json:"data"`
}

// kongRoute represents a Kong route from the Admin API.
type kongRoute struct {
	ID      string   `json:"id"`
	Paths   []string `json:"paths"`
	Methods []string `json:"methods"`
}

type kongRoutesResponse struct {
	Data []kongRoute `json:"data"`
}

// kongPlugin represents a Kong plugin from the Admin API.
type kongPlugin struct {
	Name string `json:"name"`
}

type kongPluginsResponse struct {
	Data []kongPlugin `json:"data"`
}

// Discover lists all services and their routes from Kong's Admin API.
func (k *KongAdapter) Discover(ctx context.Context, adminURL string) ([]DiscoveredAPI, error) {
	// 1. Get all services
	servicesURL := adminURL + "/services"
	servicesBody, err := k.doGet(ctx, servicesURL)
	if err != nil {
		return nil, fmt.Errorf("list kong services: %w", err)
	}

	var services kongServicesResponse
	if err := json.Unmarshal(servicesBody, &services); err != nil {
		return nil, fmt.Errorf("decode kong services: %w", err)
	}

	var apis []DiscoveredAPI
	for _, svc := range services.Data {
		api := DiscoveredAPI{
			Name:     svc.Name,
			IsActive: svc.Enabled,
		}
		if svc.Name == "" {
			api.Name = svc.ID
		}

		// Build backend URL
		backendPath := svc.Path
		if backendPath == "" {
			backendPath = ""
		}
		api.BackendURL = fmt.Sprintf("%s://%s:%d%s", svc.Protocol, svc.Host, svc.Port, backendPath)

		// 2. Get routes for this service
		routesURL := fmt.Sprintf("%s/services/%s/routes", adminURL, svc.ID)
		routesBody, err := k.doGet(ctx, routesURL)
		if err == nil {
			var routes kongRoutesResponse
			if json.Unmarshal(routesBody, &routes) == nil {
				for _, route := range routes.Data {
					api.Paths = append(api.Paths, route.Paths...)
					api.Methods = append(api.Methods, route.Methods...)
				}
			}
		}

		// 3. Get plugins for this service
		pluginsURL := fmt.Sprintf("%s/services/%s/plugins", adminURL, svc.ID)
		pluginsBody, err := k.doGet(ctx, pluginsURL)
		if err == nil {
			var plugins kongPluginsResponse
			if json.Unmarshal(pluginsBody, &plugins) == nil {
				for _, p := range plugins.Data {
					api.Policies = append(api.Policies, p.Name)
				}
			}
		}

		apis = append(apis, api)
	}

	return apis, nil
}

// ApplyPolicy pushes a plugin configuration to Kong via declarative config reload.
func (k *KongAdapter) ApplyPolicy(ctx context.Context, adminURL string, apiName string, policy PolicyAction) error {
	// Kong DB-less: GET full state → merge plugin → POST /config
	// For simplicity, we use the per-service plugin endpoint when available
	pluginURL := fmt.Sprintf("%s/services/%s/plugins", adminURL, apiName)

	pluginPayload := map[string]interface{}{
		"name":   policy.Type,
		"config": policy.Config,
		"tags":   []string{"stoa-managed"},
	}
	data, err := json.Marshal(pluginPayload)
	if err != nil {
		return fmt.Errorf("marshal kong plugin: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, pluginURL, strings.NewReader(string(data)))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	k.setAuth(req)

	resp, err := k.client.Do(req)
	if err != nil {
		return fmt.Errorf("apply kong plugin: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("kong plugin apply failed (%d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// RemovePolicy removes a plugin from a Kong service by type.
func (k *KongAdapter) RemovePolicy(ctx context.Context, adminURL string, apiName string, policyType string) error {
	// List plugins for the service, find by name, delete by ID
	pluginsURL := fmt.Sprintf("%s/services/%s/plugins", adminURL, apiName)
	body, err := k.doGet(ctx, pluginsURL)
	if err != nil {
		return fmt.Errorf("list kong plugins: %w", err)
	}

	var plugins kongPluginsResponse
	if err := json.Unmarshal(body, &plugins); err != nil {
		return fmt.Errorf("decode kong plugins: %w", err)
	}

	// Find plugin ID by name from raw JSON (we need the id field)
	var rawPlugins struct {
		Data []map[string]interface{} `json:"data"`
	}
	if err := json.Unmarshal(body, &rawPlugins); err != nil {
		return fmt.Errorf("decode kong plugins raw: %w", err)
	}

	for _, p := range rawPlugins.Data {
		name, _ := p["name"].(string)
		id, _ := p["id"].(string)
		if name == policyType && id != "" {
			deleteURL := fmt.Sprintf("%s/plugins/%s", adminURL, id)
			req, err := http.NewRequestWithContext(ctx, http.MethodDelete, deleteURL, nil)
			if err != nil {
				return err
			}
			k.setAuth(req)

			resp, err := k.client.Do(req)
			if err != nil {
				return fmt.Errorf("delete kong plugin: %w", err)
			}
			resp.Body.Close()
			return nil
		}
	}

	return nil // Plugin not found — idempotent
}

func (k *KongAdapter) doGet(ctx context.Context, url string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	k.setAuth(req)

	resp, err := k.client.Do(req)
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

func (k *KongAdapter) setAuth(req *http.Request) {
	if k.cfg.Token != "" {
		req.Header.Set("Kong-Admin-Token", k.cfg.Token)
	}
}
