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

// sendAPIWrite performs an authenticated POST/PUT to the webMethods API import
// endpoint and returns (status, body, err). Used for the initial write and
// for the 409→PUT fallback retry in C.2, so the call shape stays consistent.
func (w *WebMethodsAdapter) sendAPIWrite(ctx context.Context, method, url string, data []byte) (int, []byte, error) {
	req, err := http.NewRequestWithContext(ctx, method, url, strings.NewReader(string(data)))
	if err != nil {
		return 0, nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	w.setAuth(req)
	resp, err := w.client.Do(req)
	if err != nil {
		return 0, nil, err
	}
	body, _ := io.ReadAll(resp.Body)
	_ = resp.Body.Close()
	return resp.StatusCode, body, nil
}

// trackFailure records a per-deployment failure and appends to the batch-level
// error list. Both writes happen only when DeploymentID is set; routes without
// a DeploymentID only contribute to the global syncErrors slice.
func trackFailure(result *SyncResult, syncErrors *[]string, deploymentID, wmName, routeErr, globalDetail string) {
	*syncErrors = append(*syncErrors, wmName+": "+globalDetail)
	if deploymentID != "" {
		result.FailedRoutes[deploymentID] = routeErr
	}
}

// SyncRoutes pushes CP routes to webMethods via REST API import.
// Idempotent: checks if API exists by name, uses PUT to update if so, POST only for new APIs.
// Deactivated routes are deactivated on the gateway. Skips unchanged routes via SpecHash.
//
// The returned SyncResult.FailedRoutes map is allocated per call and never
// shared between goroutines, so concurrent SyncRoutes invocations (polling +
// SSE) produce isolated results. See C.3/C.6 in BUG-REPORT-GO-1.md.
//
// Failure resilience (C.2 / C.4 / C.5):
//   - 409 after POST triggers a single re-list + PUT fallback (no retry loop).
//     If the refreshed list locates the API, its ID is written back into the
//     in-memory existingAPIs snapshot so downstream verify/activate use the
//     fresh value. If the API is absent from the re-list ("ghost conflict"),
//     the route is marked failed — no retry.
//   - 409 after PUT is a persistent version/content conflict: tracked in
//     FailedRoutes, SpecHash not updated, batch continues.
//   - DeactivateAPI and verifyAndActivate failures no longer halt the batch:
//     they are recorded in FailedRoutes for the affected route and the loop
//     advances to the next route. Previously a single bad route caused every
//     subsequent route in the batch to be classified `applied` by default.
//
// SpecHash is updated only after the route reaches a final 2xx status AND
// verifyAndActivate returns nil — any earlier exit path leaves the hash so
// the next cycle retries.
func (w *WebMethodsAdapter) SyncRoutes(ctx context.Context, adminURL string, routes []Route) (SyncResult, error) {
	result := SyncResult{FailedRoutes: make(map[string]string)}

	existingAPIs, err := w.listAPIsIndexedByName(ctx, adminURL)
	if err != nil {
		return result, fmt.Errorf("list existing apis: %w", err)
	}

	var syncErrors []string

	// L.1 (GO-1): sanitizeWMName can collapse two distinct route names
	// (e.g. "foo/bar" and "foo bar") to the same webMethods apiName.
	// Silent collision means the second route's PUT overwrites the first's
	// definition on the gateway with no error surface. Log a warning when
	// a collision is detected so operators can investigate. Non-blocking:
	// the existing overwrite semantics are preserved (scope of P2 cleanup
	// is "make observable", not "harden with new errors").
	nameCollisions := make(map[string]string)

	for _, route := range routes {
		wmName := sanitizeWMName("stoa-" + route.Name)
		if prev, collision := nameCollisions[wmName]; collision && prev != route.Name {
			log.Printf("warn: webmethods sanitizeWMName collision — routes %q and %q both map to %q; later PUT will overwrite earlier",
				prev, route.Name, wmName)
		}
		nameCollisions[wmName] = route.Name

		// Deactivated route: deactivate on gateway if it exists.
		// C.5: deactivate failure is tracked, not returned — the batch continues.
		if !route.Activated {
			if existingID, exists := existingAPIs[wmName]; exists {
				if err := w.DeactivateAPI(ctx, adminURL, existingID); err != nil {
					trackFailure(&result, &syncErrors,
						route.DeploymentID, wmName,
						fmt.Sprintf("webmethods deactivate failed: %v", err),
						fmt.Sprintf("deactivate failed: %v", err),
					)
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
			spec = stripResponseSchemas(spec)
		}

		apiPayload := buildSyncPayload(route, wmName, spec)
		data, err := json.Marshal(apiPayload)
		if err != nil {
			trackFailure(&result, &syncErrors,
				route.DeploymentID, wmName,
				fmt.Sprintf("webmethods marshal failed: %v", err),
				fmt.Sprintf("marshal failed: %v", err),
			)
			continue
		}
		// H.1 (GO-1): fixExternalDocs was previously applied here to `data`
		// too, but this call was dead code — the wrapper payload has no
		// top-level externalDocs (the spec is nested inside apiDefinition
		// as json.RawMessage, so the Unmarshal-to-map walk never entered
		// it). The walk at line 170 on the raw spec is the sole effective
		// site.

		// Initial method + URL selection.
		var method, apiURL string
		apiID, existing := existingAPIs[wmName]
		if existing {
			method = http.MethodPut
			apiURL = fmt.Sprintf("%s/rest/apigateway/apis/%s", adminURL, apiID)
		} else {
			method = http.MethodPost
			apiURL = adminURL + "/rest/apigateway/apis"
		}

		status, respBody, err := w.sendAPIWrite(ctx, method, apiURL, data)
		if err != nil {
			trackFailure(&result, &syncErrors,
				route.DeploymentID, wmName,
				fmt.Sprintf("webmethods sync request failed: %v", err),
				fmt.Sprintf("sync request failed: %v", err),
			)
			continue
		}

		// C.2: structured 409 handling.
		if status == http.StatusConflict {
			if method == http.MethodPost {
				// Re-list once to locate the conflicting API, then PUT.
				refreshed, relistErr := w.listAPIsIndexedByName(ctx, adminURL)
				if relistErr != nil {
					trackFailure(&result, &syncErrors,
						route.DeploymentID, wmName,
						fmt.Sprintf("webmethods 409 on POST and re-list failed: %v", relistErr),
						fmt.Sprintf("409 on POST + re-list failed: %v", relistErr),
					)
					continue
				}
				foundID, ok := refreshed[wmName]
				if !ok {
					trackFailure(&result, &syncErrors,
						route.DeploymentID, wmName,
						"webmethods 409 on POST but API not present in re-list (ghost conflict or indexer lag)",
						"409 POST ghost (API not in re-list)",
					)
					continue
				}
				// Refresh local snapshot so the rest of the batch + downstream
				// verifyAndActivate see the fresh ID.
				existingAPIs[wmName] = foundID
				apiID = foundID

				retryURL := fmt.Sprintf("%s/rest/apigateway/apis/%s", adminURL, foundID)
				retryStatus, retryBody, retryErr := w.sendAPIWrite(ctx, http.MethodPut, retryURL, data)
				if retryErr != nil {
					trackFailure(&result, &syncErrors,
						route.DeploymentID, wmName,
						fmt.Sprintf("webmethods 409→PUT fallback request failed: %v", retryErr),
						fmt.Sprintf("409→PUT fallback request failed: %v", retryErr),
					)
					continue
				}
				if retryStatus == http.StatusConflict {
					trackFailure(&result, &syncErrors,
						route.DeploymentID, wmName,
						"webmethods 409 persistent conflict after POST→PUT fallback",
						"409 persistent conflict after POST→PUT fallback",
					)
					continue
				}
				if retryStatus != http.StatusOK && retryStatus != http.StatusCreated {
					detail := string(retryBody)
					if len(detail) > 300 {
						detail = detail[:300]
					}
					trackFailure(&result, &syncErrors,
						route.DeploymentID, wmName,
						fmt.Sprintf("webmethods 409→PUT fallback failed (%d): %s", retryStatus, detail),
						fmt.Sprintf("409→PUT fallback failed (%d): %s", retryStatus, detail),
					)
					continue
				}
				// Fallback succeeded — rebind status/body and fall through.
				status = retryStatus
				respBody = retryBody
			} else {
				// 409 on PUT: persistent conflict, no automatic remediation.
				trackFailure(&result, &syncErrors,
					route.DeploymentID, wmName,
					"webmethods api sync failed (409): version/content conflict on PUT",
					"409 on PUT (version/content conflict)",
				)
				continue
			}
		}

		if status != http.StatusCreated && status != http.StatusOK {
			log.Printf("webmethods: sync %s failed (%d): %s", wmName, status, string(respBody))
			detail := string(respBody)
			if len(detail) > 300 {
				detail = detail[:300]
			}
			trackFailure(&result, &syncErrors,
				route.DeploymentID, wmName,
				fmt.Sprintf("webmethods api sync failed (%d): %s", status, detail),
				fmt.Sprintf("%d — %s", status, detail),
			)
			continue
		}

		// Determine API ID for post-deploy verification.
		if apiID == "" {
			apiID = parseCreateResponseID(respBody)
			if apiID == "" {
				log.Printf("webmethods: could not parse API ID from POST response for %s, skipping activation verify", wmName)
			}
		}

		// C.4: verifyAndActivate failure is tracked per-route, not returned.
		if apiID != "" {
			if err := w.verifyAndActivate(ctx, adminURL, apiID, wmName); err != nil {
				trackFailure(&result, &syncErrors,
					route.DeploymentID, wmName,
					fmt.Sprintf("webmethods verifyAndActivate failed: %v", err),
					fmt.Sprintf("verifyAndActivate failed: %v", err),
				)
				continue
			}
		}

		// Full success — safe to record the SpecHash.
		if route.SpecHash != "" {
			w.hashesSet(wmName, route.SpecHash)
		}
	}

	if len(syncErrors) > 0 {
		return result, fmt.Errorf("webmethods api sync failed (%d/%d): %s", len(syncErrors), len(routes), strings.Join(syncErrors, "; "))
	}

	return result, nil
}
