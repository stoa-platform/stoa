package adapters

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

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
