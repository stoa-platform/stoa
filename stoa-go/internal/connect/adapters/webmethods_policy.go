package adapters

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
)

// wmPolicyTypeMapping maps STOA policy types to webMethods policy action types.
var wmPolicyTypeMapping = map[string]string{
	"cors":       "corsPolicy",
	"rate_limit": "throttlingPolicy",
	"logging":    "logInvocationPolicy",
	"jwt":        "jwtPolicy",
	"ip_filter":  "ipFilterPolicy",
}

// mapPolicyConfig converts STOA-format config to webMethods-specific parameters.
//
// The jwtPolicy and ipFilterPolicy cases were added to close GO-1 H.4
// (BUG-REPORT-GO-1.md) — previously they fell through to the default
// passthrough, sending STOA's raw config to webMethods which rejected with
// 400 "invalid policy params" (direct impact on CAB-2079 Auth/RBAC for the
// BDF demo).
//
// WM-10.15-HYPOTHESIS: the exact webMethods 10.15 parameter names below
// (jwtIssuer / jwtAudience / jwksURL / requiredClaims for jwtPolicy;
// ipFilterMode / ipList for ipFilterPolicy) are a best-effort mapping drawn
// from webMethods doc patterns but not confirmed against a live 10.15
// instance. MUST VALIDATE in staging before BDF demo — see ticket CAB-2161.
// If field names differ, update the cases below and remove this comment.
func mapPolicyConfig(wmType string, config map[string]interface{}) map[string]interface{} {
	switch wmType {
	case "corsPolicy":
		return map[string]interface{}{
			"allowedOrigins":   getOrDefault(config, "allowedOrigins", []interface{}{"*"}),
			"allowedMethods":   getOrDefault(config, "allowedMethods", []interface{}{"GET"}),
			"allowedHeaders":   getOrDefault(config, "allowedHeaders", []interface{}{}),
			"exposeHeaders":    getOrDefault(config, "exposeHeaders", []interface{}{}),
			"maxAge":           getOrDefault(config, "maxAge", 3600),
			"allowCredentials": getOrDefault(config, "allowCredentials", false),
		}
	case "throttlingPolicy":
		return map[string]interface{}{
			"maxRequestCount":   getOrDefault(config, "maxRequests", 100),
			"intervalInSeconds": getOrDefault(config, "intervalSeconds", 60),
		}
	case "logInvocationPolicy":
		return map[string]interface{}{
			"logRequestPayload":  getOrDefault(config, "logRequest", true),
			"logResponsePayload": getOrDefault(config, "logResponse", true),
		}
	case "jwtPolicy":
		// WM-10.15-HYPOTHESIS (CAB-2161) — validate in staging.
		return map[string]interface{}{
			"jwtIssuer":      getOrDefault(config, "issuer", ""),
			"jwtAudience":    getOrDefault(config, "audience", ""),
			"jwksURL":        getOrDefault(config, "jwks_url", ""),
			"requiredClaims": getOrDefault(config, "required_claims", map[string]interface{}{}),
		}
	case "ipFilterPolicy":
		// WM-10.15-HYPOTHESIS (CAB-2161) — validate in staging.
		// mode uppercased to match the broader fixSecuritySchemeTypes
		// convention (webMethods enum values are uppercase).
		mode, _ := getOrDefault(config, "mode", "allow").(string)
		return map[string]interface{}{
			"ipFilterMode": upperASCII(mode),
			"ipList":       getOrDefault(config, "ip_list", []interface{}{}),
		}
	default:
		return config
	}
}

// upperASCII uppercases an ASCII string without pulling in strings.ToUpper,
// which would also touch non-ASCII code points. The enum values we care
// about (allow/deny) are ASCII-only.
func upperASCII(s string) string {
	out := make([]byte, len(s))
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c >= 'a' && c <= 'z' {
			c -= 'a' - 'A'
		}
		out[i] = c
	}
	return string(out)
}

func getOrDefault(config map[string]interface{}, key string, defaultVal interface{}) interface{} {
	if v, ok := config[key]; ok {
		return v
	}
	return defaultVal
}

// findPolicyByType searches for an existing policy action by type on a given API.
// Returns the policy ID, or "" if not found.
func (w *WebMethodsAdapter) findPolicyByType(ctx context.Context, adminURL string, apiID string, wmType string, stoaType string) (string, error) {
	policiesURL := fmt.Sprintf("%s/rest/apigateway/apis/%s/policyActions", adminURL, apiID)
	body, err := w.doGet(ctx, policiesURL)
	if err != nil {
		return "", err
	}

	var policies struct {
		PolicyActions []wmPolicyAction `json:"policyActions"`
	}
	if err := json.Unmarshal(body, &policies); err != nil {
		return "", err
	}

	for _, p := range policies.PolicyActions {
		if p.TemplateKey == wmType || p.TemplateKey == stoaType {
			return p.ID, nil
		}
	}
	return "", nil
}

// ApplyPolicy upserts a policy action on a webMethods API.
// Flow: resolve API ID → list existing policies → PUT if exists, POST if new.
func (w *WebMethodsAdapter) ApplyPolicy(ctx context.Context, adminURL string, apiName string, policy PolicyAction) error {
	apiID, err := w.resolveAPIID(ctx, adminURL, apiName)
	if err != nil {
		return err
	}

	wmType, ok := wmPolicyTypeMapping[policy.Type]
	if !ok {
		wmType = policy.Type
	}

	existingID, err := w.findPolicyByType(ctx, adminURL, apiID, wmType, policy.Type)
	if err != nil {
		return fmt.Errorf("find existing policy: %w", err)
	}

	policyAction := map[string]interface{}{
		"policyActionName": fmt.Sprintf("stoa-%s-%s", apiName, policy.Type),
		"type":             wmType,
		"parameters":       mapPolicyConfig(wmType, policy.Config),
	}

	payload := map[string]interface{}{
		"policyAction": policyAction,
		"apiId":        apiID,
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal policy action: %w", err)
	}

	var method, reqURL string
	if existingID != "" {
		method = http.MethodPut
		reqURL = fmt.Sprintf("%s/rest/apigateway/policyActions/%s", adminURL, existingID)
	} else {
		method = http.MethodPost
		reqURL = adminURL + "/rest/apigateway/policyActions"
	}

	req, err := http.NewRequestWithContext(ctx, method, reqURL, bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	w.setAuth(req)

	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("apply webmethods policy: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("webmethods policy apply failed (%d): %s", resp.StatusCode, string(respBody))
	}

	return nil
}

// RemovePolicy removes every policy action of the given type from a webMethods
// API. Flow: resolve API ID → list policy actions for API → DELETE all matches.
//
// Idempotent on 0 matches (returns nil). When multiple matches exist — a
// symptom of a prior apply race, a crashed apply that left an orphan, or an
// upgrade that re-created the policy under a different name — every match is
// deleted and the count is logged. Pre-GO-1, only the first match was removed
// (C.1 in BUG-REPORT-GO-1.md), leaving the rest silently active on the
// gateway.
//
// Error semantics:
//   - N matches, all deleted successfully → nil (log at N > 1).
//   - N matches, M ≥ 1 deletions failed → error wrapping the last failure,
//     with an "removed X/N" prefix so ops can gauge impact.
//   - 0 matches → nil (caller treats as already-removed).
func (w *WebMethodsAdapter) RemovePolicy(ctx context.Context, adminURL string, apiName string, policyType string) error {
	apiID, err := w.resolveAPIID(ctx, adminURL, apiName)
	if err != nil {
		return err
	}

	wmType, ok := wmPolicyTypeMapping[policyType]
	if !ok {
		wmType = policyType
	}

	policiesURL := fmt.Sprintf("%s/rest/apigateway/apis/%s/policyActions", adminURL, apiID)
	body, err := w.doGet(ctx, policiesURL)
	if err != nil {
		return fmt.Errorf("list policies for removal: %w", err)
	}

	var policies struct {
		PolicyActions []wmPolicyAction `json:"policyActions"`
	}
	if err := json.Unmarshal(body, &policies); err != nil {
		return fmt.Errorf("decode policy actions: %w", err)
	}

	var matches []wmPolicyAction
	for _, p := range policies.PolicyActions {
		if p.TemplateKey == wmType || p.TemplateKey == policyType {
			matches = append(matches, p)
		}
	}
	if len(matches) == 0 {
		return nil // idempotent
	}

	var lastErr error
	succeeded := 0
	for _, p := range matches {
		deleteURL := fmt.Sprintf("%s/rest/apigateway/policyActions/%s", adminURL, p.ID)
		req, err := http.NewRequestWithContext(ctx, http.MethodDelete, deleteURL, nil)
		if err != nil {
			lastErr = err
			continue
		}
		w.setAuth(req)

		resp, err := w.client.Do(req)
		if err != nil {
			lastErr = fmt.Errorf("delete webmethods policy %s: %w", p.ID, err)
			continue
		}
		_ = resp.Body.Close()

		if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
			lastErr = fmt.Errorf("webmethods policy delete %s failed (%d)", p.ID, resp.StatusCode)
			continue
		}
		succeeded++
	}

	if len(matches) > 1 {
		log.Printf("webmethods: RemovePolicy removed %d/%d duplicate policy actions for API=%s type=%s",
			succeeded, len(matches), apiName, policyType)
	}
	if lastErr != nil {
		return fmt.Errorf("webmethods RemovePolicy: removed %d/%d policies for API=%s type=%s; last error: %w",
			succeeded, len(matches), apiName, policyType, lastErr)
	}
	return nil
}
