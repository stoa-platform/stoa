package adapters

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

// InjectCredentials provisions applications and API associations on webMethods.
// Two-step process: (1) create application, (2) associate with APIs.
func (w *WebMethodsAdapter) InjectCredentials(ctx context.Context, adminURL string, creds []Credential) error {
	for _, cred := range creds {
		// Step 1: Create application
		appPayload := map[string]interface{}{
			"name":        "stoa-" + cred.ConsumerID,
			"description": fmt.Sprintf("STOA managed consumer %s", cred.ConsumerID),
			"identifiers": []map[string]interface{}{
				{"key": cred.Key, "name": "apiKey", "value": []string{cred.Key}},
			},
		}

		data, err := json.Marshal(appPayload)
		if err != nil {
			return fmt.Errorf("marshal webmethods app: %w", err)
		}

		appURL := adminURL + "/rest/apigateway/applications"
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, appURL, strings.NewReader(string(data)))
		if err != nil {
			return err
		}
		req.Header.Set("Content-Type", "application/json")
		w.setAuth(req)

		resp, err := w.client.Do(req)
		if err != nil {
			return fmt.Errorf("create webmethods application: %w", err)
		}

		respBody, _ := io.ReadAll(resp.Body)
		_ = resp.Body.Close()

		if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusConflict {
			return fmt.Errorf("webmethods app create failed (%d): %s", resp.StatusCode, string(respBody))
		}

		var appResp struct {
			ID string `json:"id"`
		}
		if err := json.Unmarshal(respBody, &appResp); err != nil || appResp.ID == "" {
			// If we can't get the ID (e.g., 409 Conflict), skip association
			continue
		}

		// Step 2: Associate application with APIs
		if cred.APIName != "" {
			apiID, err := w.resolveAPIID(ctx, adminURL, cred.APIName)
			if err != nil {
				return fmt.Errorf("resolve API for credential association: %w", err)
			}

			assocPayload := map[string]interface{}{
				"apiIDs": []string{apiID},
			}
			assocData, err := json.Marshal(assocPayload)
			if err != nil {
				return fmt.Errorf("marshal api association: %w", err)
			}

			assocURL := fmt.Sprintf("%s/rest/apigateway/applications/%s/apis", adminURL, appResp.ID)
			assocReq, err := http.NewRequestWithContext(ctx, http.MethodPost, assocURL, strings.NewReader(string(assocData)))
			if err != nil {
				return err
			}
			assocReq.Header.Set("Content-Type", "application/json")
			w.setAuth(assocReq)

			assocResp, err := w.client.Do(assocReq)
			if err != nil {
				return fmt.Errorf("associate webmethods app with api: %w", err)
			}
			_ = assocResp.Body.Close()

			if assocResp.StatusCode != http.StatusOK && assocResp.StatusCode != http.StatusCreated && assocResp.StatusCode != http.StatusConflict {
				return fmt.Errorf("webmethods app-api association failed (%d)", assocResp.StatusCode)
			}
		}
	}
	return nil
}
