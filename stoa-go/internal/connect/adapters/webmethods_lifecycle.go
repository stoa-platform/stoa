package adapters

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
)

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

// ActivateAPI activates a webMethods API by ID.
func (w *WebMethodsAdapter) ActivateAPI(ctx context.Context, adminURL string, apiID string) error {
	reqURL := fmt.Sprintf("%s/rest/apigateway/apis/%s/activate", adminURL, apiID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPut, reqURL, nil)
	if err != nil {
		return err
	}
	w.setAuth(req)

	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("activate webmethods api: %w", err)
	}
	_ = resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		return fmt.Errorf("webmethods api activate failed (%d)", resp.StatusCode)
	}
	return nil
}

// DeactivateAPI deactivates a webMethods API by ID.
func (w *WebMethodsAdapter) DeactivateAPI(ctx context.Context, adminURL string, apiID string) error {
	reqURL := fmt.Sprintf("%s/rest/apigateway/apis/%s/deactivate", adminURL, apiID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPut, reqURL, nil)
	if err != nil {
		return err
	}
	w.setAuth(req)

	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("deactivate webmethods api: %w", err)
	}
	_ = resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		return fmt.Errorf("webmethods api deactivate failed (%d)", resp.StatusCode)
	}
	return nil
}

// DeleteAPI removes an API from webMethods (2-step: deactivate then delete).
// Idempotent: returns nil if the API does not exist.
func (w *WebMethodsAdapter) DeleteAPI(ctx context.Context, adminURL string, apiName string) error {
	apiID, err := w.resolveAPIID(ctx, adminURL, apiName)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			return nil // idempotent
		}
		return err
	}

	// Step 1: deactivate (ignore errors, may already be inactive)
	_ = w.DeactivateAPI(ctx, adminURL, apiID)

	// Step 2: delete
	reqURL := fmt.Sprintf("%s/rest/apigateway/apis/%s", adminURL, apiID)
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, reqURL, nil)
	if err != nil {
		return err
	}
	w.setAuth(req)

	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("delete webmethods api: %w", err)
	}
	_ = resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent && resp.StatusCode != http.StatusNotFound {
		return fmt.Errorf("webmethods api delete failed (%d)", resp.StatusCode)
	}
	return nil
}

// verifyAndActivate checks that an API is active on webMethods after PUT/POST,
// and activates it if not. Returns error if activation fails.
func (w *WebMethodsAdapter) verifyAndActivate(ctx context.Context, adminURL, apiID, apiName string) error {
	detailURL := fmt.Sprintf("%s/rest/apigateway/apis/%s", adminURL, apiID)
	body, err := w.doGet(ctx, detailURL)
	if err != nil {
		return fmt.Errorf("verify webmethods api %s (%s): %w", apiName, apiID, err)
	}

	// Parse response — try nested shape first, then flat
	var wrapper struct {
		APIResponse wmAPIWrapper `json:"apiResponse"`
	}
	var isActive bool
	if err := json.Unmarshal(body, &wrapper); err == nil && wrapper.APIResponse.API.ID != "" {
		isActive = wrapper.APIResponse.API.IsActive
	} else {
		var flat wmAPI
		if err := json.Unmarshal(body, &flat); err == nil && flat.ID != "" {
			isActive = flat.IsActive
		} else {
			// Cannot determine status — treat as active to avoid false negatives
			return nil
		}
	}

	if isActive {
		log.Printf("webmethods: verifyAndActivate %s (%s): already active", apiName, apiID)
		return nil
	}

	// API is not active — attempt activation
	log.Printf("webmethods: verifyAndActivate %s (%s): isActive=false, activating...", apiName, apiID)
	if err := w.ActivateAPI(ctx, adminURL, apiID); err != nil {
		return fmt.Errorf("API created but activation failed on webMethods: %s (%s): %w", apiName, apiID, err)
	}
	log.Printf("webmethods: verifyAndActivate %s (%s): activated successfully", apiName, apiID)
	return nil
}
