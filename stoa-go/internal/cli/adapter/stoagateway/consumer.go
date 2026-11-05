package stoagateway

import (
	"context"
	"errors"
)

// VerifyConsumer checks the live route without provisioning credentials. The
// gateway's identity provider owns consumer credentials; admin credentials are
// never sent to the data plane.
func (a *Adapter) VerifyConsumer(ctx context.Context, want Contract) (string, error) {
	live, found, err := a.request(ctx, "GET", contractPath(want), nil)
	if err != nil {
		return "", err
	}
	if !found || !owned(live, want) {
		return "", errors.New("owned live contract required")
	}
	return a.probe(ctx, live)
}
