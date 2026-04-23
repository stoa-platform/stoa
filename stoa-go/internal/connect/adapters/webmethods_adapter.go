package adapters

import (
	"context"
	"net/http"
	"sync"
	"time"
)

// WebMethodsAdapter implements GatewayAdapter for webMethods API Gateway (port 5555).
//
// Thread-safety: a single WebMethodsAdapter instance is shared by the
// polling goroutine (RunRouteSync) and the SSE goroutine
// (handleSyncDeployment). syncedHashes reads/writes MUST be guarded by
// hashesMu — see C.3 in BUG-REPORT-GO-1.md.
type WebMethodsAdapter struct {
	client *http.Client
	cfg    AdapterConfig

	hashesMu     sync.Mutex
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
//
// GO-1 M.3: network errors are now propagated to the caller instead of
// silently returning (false, nil). autoDetect (internal/connect/discovery.go)
// already logs and skips to the next adapter when err is non-nil, so the
// auto-detection contract stays "try next gateway on unreachable" — but
// now the error is visible in logs instead of indistinguishable from
// "reachable but not webMethods".
func (w *WebMethodsAdapter) Detect(ctx context.Context, adminURL string) (bool, error) {
	url := adminURL + "/rest/apigateway/health"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return false, err
	}
	w.setAuth(req)

	resp, err := w.client.Do(req)
	if err != nil {
		return false, err
	}
	defer func() { _ = resp.Body.Close() }()

	return resp.StatusCode == http.StatusOK, nil
}
