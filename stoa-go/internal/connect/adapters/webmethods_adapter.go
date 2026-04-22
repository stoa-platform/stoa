package adapters

import (
	"context"
	"net/http"
	"time"
)

// WebMethodsAdapter implements GatewayAdapter for webMethods API Gateway (port 5555).
type WebMethodsAdapter struct {
	client       *http.Client
	cfg          AdapterConfig
	syncedHashes map[string]string // tracks last-synced SpecHash per route name
	FailedRoutes map[string]string // deployment_id → error (populated after SyncRoutes)
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

// GetFailedRoutes returns the per-deployment-id error map from the last SyncRoutes call.
func (w *WebMethodsAdapter) GetFailedRoutes() map[string]string {
	return w.FailedRoutes
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
