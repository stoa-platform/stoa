package adapters

import (
	"context"
	"fmt"
)

// UpsertAlias creates or updates an endpoint alias on webMethods.
func (w *WebMethodsAdapter) UpsertAlias(ctx context.Context, adminURL string, spec AliasSpec) error {
	aliasType := spec.Type
	if aliasType == "" {
		aliasType = "endpoint"
	}
	connTimeout := spec.ConnectionTimeout
	if connTimeout == 0 {
		connTimeout = 30
	}
	readTimeout := spec.ReadTimeout
	if readTimeout == 0 {
		readTimeout = 60
	}
	optimization := spec.Optimization
	if optimization == "" {
		optimization = "None"
	}
	payload := map[string]interface{}{
		"name": spec.Name, "description": spec.Description, "type": aliasType,
		"endPointURI": spec.EndpointURI, "connectionTimeout": connTimeout,
		"readTimeout": readTimeout, "optimizationTechnique": optimization,
		"passSecurityHeaders": spec.PassSecurityHeaders,
	}
	existing, err := w.listAliases(ctx, adminURL)
	if err != nil {
		return err
	}
	var existingID string
	for _, a := range existing {
		if a.Name == spec.Name && a.Type != "authServerAlias" {
			existingID = a.ID
			break
		}
	}
	return w.upsertResource(ctx, adminURL, "/rest/apigateway/alias", existingID, payload)
}

// DeleteAlias removes an alias by name.
func (w *WebMethodsAdapter) DeleteAlias(ctx context.Context, adminURL string, name string) error {
	existing, err := w.listAliases(ctx, adminURL)
	if err != nil {
		return err
	}
	for _, a := range existing {
		if a.Name == name {
			return w.doDelete(ctx, fmt.Sprintf("%s/rest/apigateway/alias/%s", adminURL, a.ID))
		}
	}
	return nil
}
