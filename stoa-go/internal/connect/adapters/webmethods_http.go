package adapters

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

// doGet performs an authenticated GET and returns the body on 200, else an error including status+body.
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

// doDelete performs an authenticated DELETE and treats 200/204/404 as success.
func (w *WebMethodsAdapter) doDelete(ctx context.Context, deleteURL string) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, deleteURL, nil)
	if err != nil {
		return err
	}
	w.setAuth(req)
	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("delete resource: %w", err)
	}
	_ = resp.Body.Close()
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent && resp.StatusCode != http.StatusNotFound {
		return fmt.Errorf("delete failed (%d)", resp.StatusCode)
	}
	return nil
}

// setAuth attaches HTTP basic auth to the request when a username is configured.
func (w *WebMethodsAdapter) setAuth(req *http.Request) {
	if w.cfg.Username != "" {
		req.SetBasicAuth(w.cfg.Username, w.cfg.Password)
	}
}

// upsertResource POSTs a new resource or PUTs an update at basePath.
// 200/201/409 are accepted; other statuses return an error carrying the body.
func (w *WebMethodsAdapter) upsertResource(ctx context.Context, adminURL string, basePath string, existingID string, payload map[string]interface{}) error {
	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal resource: %w", err)
	}
	var method, resourceURL string
	if existingID != "" {
		method = http.MethodPut
		resourceURL = fmt.Sprintf("%s%s/%s", adminURL, basePath, existingID)
	} else {
		method = http.MethodPost
		resourceURL = adminURL + basePath
	}
	req, err := http.NewRequestWithContext(ctx, method, resourceURL, bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	w.setAuth(req)
	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("upsert resource: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusConflict {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("upsert failed (%d): %s", resp.StatusCode, string(respBody))
	}
	return nil
}
