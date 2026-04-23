package adapters

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
)

// buildSyncPayload constructs the webMethods API payload for a single route.
// If an OpenAPI/Swagger spec is present, wrap it in apiDefinition and let webMethods
// derive endpoints/resources. Otherwise build a minimal REST API definition manually.
func buildSyncPayload(route Route, wmName string, spec []byte) map[string]interface{} {
	if len(spec) > 0 {
		specType := "openapi"
		if bytes.Contains(spec, []byte(`"swagger"`)) {
			specType = "swagger"
		}
		return map[string]interface{}{
			"apiName":       wmName,
			"apiVersion":    "1.0",
			"type":          specType,
			"apiDefinition": json.RawMessage(spec),
		}
	}
	return map[string]interface{}{
		"apiName":        wmName,
		"apiVersion":     "1.0",
		"apiDescription": fmt.Sprintf("STOA managed route %s", route.Name),
		"type":           "REST",
		"isActive":       true,
		"nativeEndpoint": []map[string]interface{}{
			{"uri": route.BackendURL},
		},
		"resources": []map[string]interface{}{
			{"resourcePath": route.PathPrefix, "methods": route.Methods},
		},
		"tags": []string{"stoa-managed"},
	}
}

// parseCreateResponseID extracts an API ID from a webMethods POST response body.
// Handles both nested (apiResponse.api.id) and flat (top-level id) shapes.
// Returns "" when the ID cannot be determined.
func parseCreateResponseID(respBody []byte) string {
	var createResp struct {
		APIResponse struct {
			API struct {
				ID string `json:"id"`
			} `json:"api"`
		} `json:"apiResponse"`
		ID string `json:"id"`
	}
	if err := json.Unmarshal(respBody, &createResp); err != nil {
		return ""
	}
	if createResp.APIResponse.API.ID != "" {
		return createResp.APIResponse.API.ID
	}
	return createResp.ID
}

// hashesGet reads syncedHashes[name] under lock.
func (w *WebMethodsAdapter) hashesGet(name string) (string, bool) {
	w.hashesMu.Lock()
	defer w.hashesMu.Unlock()
	v, ok := w.syncedHashes[name]
	return v, ok
}

// hashesSet writes syncedHashes[name] = hash under lock.
func (w *WebMethodsAdapter) hashesSet(name, hash string) {
	w.hashesMu.Lock()
	defer w.hashesMu.Unlock()
	w.syncedHashes[name] = hash
}

// SyncRoutes pushes CP routes to webMethods via REST API import.
// Idempotent: checks if API exists by name, uses PUT to update if so, POST only for new APIs.
// Deactivated routes are deactivated on the gateway. Skips unchanged routes via SpecHash.
//
// The returned SyncResult.FailedRoutes map is allocated per call and never
// shared between goroutines, so concurrent SyncRoutes invocations (polling +
// SSE) produce isolated results. See C.3/C.6 in BUG-REPORT-GO-1.md.
func (w *WebMethodsAdapter) SyncRoutes(ctx context.Context, adminURL string, routes []Route) (SyncResult, error) {
	result := SyncResult{FailedRoutes: make(map[string]string)}

	existingAPIs, err := w.listAPIsIndexedByName(ctx, adminURL)
	if err != nil {
		return result, fmt.Errorf("list existing apis: %w", err)
	}

	var syncErrors []string

	for _, route := range routes {
		wmName := sanitizeWMName("stoa-" + route.Name)

		// Deactivated route: deactivate on gateway if it exists
		if !route.Activated {
			if existingID, exists := existingAPIs[wmName]; exists {
				if err := w.DeactivateAPI(ctx, adminURL, existingID); err != nil {
					return result, fmt.Errorf("deactivate route %s: %w", route.Name, err)
				}
			}
			continue
		}

		// SpecHash reconciliation: skip if unchanged since last sync
		if route.SpecHash != "" {
			if lastHash, ok := w.hashesGet(wmName); ok && lastHash == route.SpecHash {
				continue
			}
		}

		// Fix spec compatibility issues before sending to webMethods
		spec := route.OpenAPISpec
		if len(spec) > 0 {
			spec = downgradeOpenAPI31(spec)
			spec = fixExternalDocs(spec)
			spec = fixSecuritySchemeTypes(spec)
			spec = stripSwagger2ResponseRefs(spec)
		}

		apiPayload := buildSyncPayload(route, wmName, spec)
		data, err := json.Marshal(apiPayload)
		if err != nil {
			return result, fmt.Errorf("marshal webmethods api: %w", err)
		}
		data = fixExternalDocs(data)

		var method, apiURL string
		if existingID, exists := existingAPIs[wmName]; exists {
			method = http.MethodPut
			apiURL = fmt.Sprintf("%s/rest/apigateway/apis/%s", adminURL, existingID)
		} else {
			method = http.MethodPost
			apiURL = adminURL + "/rest/apigateway/apis"
		}

		req, err := http.NewRequestWithContext(ctx, method, apiURL, strings.NewReader(string(data)))
		if err != nil {
			return result, err
		}
		req.Header.Set("Content-Type", "application/json")
		w.setAuth(req)

		resp, err := w.client.Do(req)
		if err != nil {
			return result, fmt.Errorf("sync webmethods api: %w", err)
		}
		respBody, _ := io.ReadAll(resp.Body)
		_ = resp.Body.Close()

		if resp.StatusCode == http.StatusConflict {
			continue
		}
		if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
			log.Printf("webmethods: sync %s failed (%d): %s", wmName, resp.StatusCode, string(respBody))
			detail := string(respBody)
			if len(detail) > 300 {
				detail = detail[:300]
			}
			errMsg := fmt.Sprintf("%s: %d — %s", wmName, resp.StatusCode, detail)
			syncErrors = append(syncErrors, errMsg)
			if route.DeploymentID != "" {
				result.FailedRoutes[route.DeploymentID] = fmt.Sprintf("webmethods api sync failed (%d): %s", resp.StatusCode, detail)
			}
			continue
		}

		// Determine API ID for post-deploy verification
		var apiID string
		if existingID, exists := existingAPIs[wmName]; exists {
			apiID = existingID
		} else {
			apiID = parseCreateResponseID(respBody)
			if apiID == "" {
				log.Printf("webmethods: could not parse API ID from POST response for %s, skipping activation verify", wmName)
			}
		}

		// Verify the API is actually active on webMethods
		if apiID != "" {
			if err := w.verifyAndActivate(ctx, adminURL, apiID, wmName); err != nil {
				return result, err
			}
		}

		if route.SpecHash != "" {
			w.hashesSet(wmName, route.SpecHash)
		}
	}

	if len(syncErrors) > 0 {
		return result, fmt.Errorf("webmethods api sync failed (%d/%d): %s", len(syncErrors), len(routes), strings.Join(syncErrors, "; "))
	}

	return result, nil
}
