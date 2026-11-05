// Package stoagateway publishes and verifies owned UAC contracts.
package stoagateway

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// Contract retains all gateway fields so rollback preserves the live document.
type Contract map[string]any

func (c Contract) String(key string) string { s, _ := c[key].(string); return s }
func (c Contract) Key() string              { return c.String("tenant_id") + ":" + c.String("name") }

// Adapter uses separate admin and data-plane origins; probes never send the admin token.
type Adapter struct {
	adminURL, gatewayURL, token string
	client                      *http.Client
	Audience                    string
	Realms                      []string
	AllowUnauthenticatedREST    bool
}

func New(adminURL, gatewayURL, token string, client *http.Client) *Adapter {
	if client == nil {
		client = &http.Client{Timeout: 15 * time.Second}
	}
	// Never forward bearer credentials to a redirect target.
	copyClient := *client
	copyClient.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	return &Adapter{adminURL: strings.TrimRight(adminURL, "/"), gatewayURL: strings.TrimRight(gatewayURL, "/"), token: token, client: &copyClient, Realms: []string{"stoa"}}
}

func (a *Adapter) request(ctx context.Context, method, path string, body Contract) (Contract, bool, error) {
	var input io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, false, err
		}
		input = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, method, a.adminURL+path, input)
	if err != nil {
		return nil, false, errors.New("invalid admin request")
	}
	req.Header.Set("Authorization", "Bearer "+a.token)
	req.Header.Set("Content-Type", "application/json")
	resp, err := a.client.Do(req)
	if err != nil {
		return nil, false, errors.New("admin request failed")
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode == 404 && method == http.MethodGet {
		return nil, false, nil
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, false, fmt.Errorf("admin request: HTTP %d", resp.StatusCode)
	}
	if method != http.MethodGet {
		return nil, true, nil
	}
	var result Contract
	if err := json.NewDecoder(io.LimitReader(resp.Body, 4<<20)).Decode(&result); err != nil {
		return nil, false, errors.New("invalid contract response")
	}
	return result, true, nil
}
func contractPath(c Contract) string { return "/admin/contracts/" + url.PathEscape(c.Key()) }
func owned(live, want Contract) bool {
	return want.String("description") != "" && live.String("description") == want.String("description")
}

// ForeignObjects is checked immediately before every write, including drift repair.
func (a *Adapter) ForeignObjects(ctx context.Context, want Contract) (bool, error) {
	live, found, err := a.request(ctx, http.MethodGet, contractPath(want), nil)
	return found && !owned(live, want), err
}
func (a *Adapter) Missing(ctx context.Context, want Contract) (bool, error) {
	var err error
	want, err = a.authenticatedContract(want)
	if err != nil {
		return false, err
	}
	live, found, err := a.request(ctx, http.MethodGet, contractPath(want), nil)
	return !found || !owned(live, want) || live.String("version") != want.String("version") || live.String("status") != "published" || !verifiedAuth(live, want), err
}
func (a *Adapter) Delete(ctx context.Context, want Contract) error {
	live, found, err := a.request(ctx, http.MethodGet, contractPath(want), nil)
	if err != nil || !found {
		return err
	}
	if !owned(live, want) {
		return errors.New("refusing to delete foreign-owned contract")
	}
	_, _, err = a.request(ctx, http.MethodDelete, contractPath(want), nil)
	return err
}
func (a *Adapter) probe(ctx context.Context, c Contract) (string, error) {
	endpoints, ok := c["endpoints"].([]any)
	if !ok || len(endpoints) == 0 {
		return "", errors.New("contract requires endpoints")
	}
	ep, ok := endpoints[0].(map[string]any)
	if !ok {
		return "", errors.New("invalid endpoint")
	}
	path, _ := ep["path"].(string)
	raw := a.gatewayURL + "/apis/" + url.PathEscape(c.String("tenant_id")) + "/" + url.PathEscape(c.String("name")) + path
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, raw, nil)
	if err != nil {
		return "", errors.New("invalid probe request")
	}
	resp, err := a.client.Do(req)
	if err != nil {
		return "", errors.New("anonymous probe failed")
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode == 401 || resp.StatusCode == 403 {
		return "enforced", nil
	}
	if a.AllowUnauthenticatedREST && c.String("classification") == "H" {
		return "unprotected", nil
	}
	return "", fmt.Errorf("anonymous probe: HTTP %d, expected 401 or 403", resp.StatusCode)
}

// Publish rolls back only failures after a successful POST. The gateway already
// rolls back binder failures inside POST /admin/contracts.
func (a *Adapter) Publish(ctx context.Context, want Contract) (string, error) {
	var err error
	want, err = a.authenticatedContract(want)
	if err != nil {
		return "", err
	}
	if want.String("name") == "" || want.String("tenant_id") == "" || want.String("version") == "" || want.String("description") == "" {
		return "", errors.New("contract identity and ownership description are required")
	}
	prev, existed, err := a.request(ctx, http.MethodGet, contractPath(want), nil)
	if err != nil {
		return "", err
	}
	if existed && !owned(prev, want) {
		return "", errors.New("drift collision: foreign-owned contract")
	}
	if _, _, err = a.request(ctx, http.MethodPost, "/admin/contracts", want); err != nil {
		return "", err
	}
	live, found, err := a.request(ctx, http.MethodGet, contractPath(want), nil)
	if err == nil && (!found || !owned(live, want) || live.String("version") != want.String("version") || live.String("status") != "published" || !verifiedAuth(live, want)) {
		err = errors.New("published contract verification failed")
	}
	var protection string
	if err == nil {
		protection, err = a.probe(ctx, want)
	}
	if err == nil {
		return protection, nil
	}
	// Rollback remains possible after caller cancellation, but has a fixed deadline.
	rollbackCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 15*time.Second)
	defer cancel()
	if rb := a.rollback(rollbackCtx, want, prev, existed); rb != nil {
		return "", fmt.Errorf("%w; rollback: %v", err, rb)
	}
	return "", err
}
func (a *Adapter) rollback(ctx context.Context, want, previous Contract, existed bool) error {
	live, found, err := a.request(ctx, http.MethodGet, contractPath(want), nil)
	if err != nil {
		return err
	}
	if found && !owned(live, want) {
		return errors.New("refusing rollback of foreign-owned contract")
	}
	if existed {
		if !a.mayRestore(previous) {
			if found {
				if _, _, err = a.request(ctx, http.MethodDelete, contractPath(want), nil); err != nil {
					return err
				}
			}
			return errors.New("refusing to restore open or generic-audience contract; classification H requires options.allowUnauthenticatedREST")
		}
		_, _, err = a.request(ctx, http.MethodPost, "/admin/contracts", previous)
		return err
	}
	if !found {
		return nil
	}
	_, _, err = a.request(ctx, http.MethodDelete, contractPath(want), nil)
	return err
}
