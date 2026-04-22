package adapters

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

// listAliases fetches all aliases from webMethods (endpoint + authServerAlias types mixed).
// Also used by the endpoint-alias path in webmethods_alias.go.
func (w *WebMethodsAdapter) listAliases(ctx context.Context, adminURL string) ([]wmAlias, error) {
	body, err := w.doGet(ctx, adminURL+"/rest/apigateway/alias")
	if err != nil {
		return nil, fmt.Errorf("list aliases: %w", err)
	}
	var resp wmAliasListResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil, fmt.Errorf("decode aliases: %w", err)
	}
	return resp.Alias, nil
}

// listStrategies fetches all strategies from webMethods.
func (w *WebMethodsAdapter) listStrategies(ctx context.Context, adminURL string) ([]wmStrategy, error) {
	body, err := w.doGet(ctx, adminURL+"/rest/apigateway/strategies")
	if err != nil {
		return nil, fmt.Errorf("list strategies: %w", err)
	}
	var resp wmStrategyListResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil, fmt.Errorf("decode strategies: %w", err)
	}
	return resp.Strategies, nil
}

// UpsertAuthServer creates or updates an OIDC auth server alias on webMethods.
func (w *WebMethodsAdapter) UpsertAuthServer(ctx context.Context, adminURL string, spec AuthServerSpec) error {
	scopes := spec.Scopes
	if len(scopes) == 0 {
		scopes = []string{"openid"}
	}
	payload := map[string]interface{}{
		"name": spec.Name, "description": spec.Description, "type": "authServerAlias",
		"discoveryURL": spec.DiscoveryURL, "introspectionURL": spec.IntrospectionURL,
		"clientId": spec.ClientID, "clientSecret": spec.ClientSecret, "scopes": scopes,
	}
	existing, err := w.listAliases(ctx, adminURL)
	if err != nil {
		return err
	}
	var existingID string
	for _, a := range existing {
		if a.Name == spec.Name && a.Type == "authServerAlias" {
			existingID = a.ID
			break
		}
	}
	return w.upsertResource(ctx, adminURL, "/rest/apigateway/alias", existingID, payload)
}

// DeleteAuthServer removes an auth server alias by name.
func (w *WebMethodsAdapter) DeleteAuthServer(ctx context.Context, adminURL string, name string) error {
	existing, err := w.listAliases(ctx, adminURL)
	if err != nil {
		return err
	}
	for _, a := range existing {
		if a.Name == name && a.Type == "authServerAlias" {
			return w.doDelete(ctx, fmt.Sprintf("%s/rest/apigateway/alias/%s", adminURL, a.ID))
		}
	}
	return nil
}

// UpsertStrategy creates or updates an OAuth2 strategy on webMethods.
func (w *WebMethodsAdapter) UpsertStrategy(ctx context.Context, adminURL string, spec StrategySpec) error {
	strategyType := spec.Type
	if strategyType == "" {
		strategyType = "OAUTH2"
	}
	payload := map[string]interface{}{
		"name": spec.Name, "description": spec.Description, "type": strategyType,
		"authServerAlias": spec.AuthServerAlias, "clientId": spec.ClientID,
		"audience": spec.Audience,
	}
	existing, err := w.listStrategies(ctx, adminURL)
	if err != nil {
		return err
	}
	var existingID string
	for _, s := range existing {
		if s.Name == spec.Name {
			existingID = s.ID
			break
		}
	}
	return w.upsertResource(ctx, adminURL, "/rest/apigateway/strategies", existingID, payload)
}

// UpsertScope creates a scope mapping on webMethods.
func (w *WebMethodsAdapter) UpsertScope(ctx context.Context, adminURL string, spec ScopeSpec) error {
	keycloakScope := spec.KeycloakScope
	if keycloakScope == "" {
		keycloakScope = "openid"
	}
	payload := map[string]interface{}{
		"scopeName": spec.ScopeName, "description": spec.Description,
		"audience": spec.Audience, "apiIds": spec.APIIDs,
		"authServerAlias": spec.AuthServerAlias, "keycloakScope": keycloakScope,
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal scope: %w", err)
	}
	scopeURL := adminURL + "/rest/apigateway/scopes"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, scopeURL, bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	w.setAuth(req)
	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("create scope: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusConflict {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("scope create failed (%d): %s", resp.StatusCode, string(respBody))
	}
	return nil
}
