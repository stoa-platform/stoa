// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package cmdflags

import (
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stoa-platform/stoa-go/pkg/client"
)

// regression for CAB-2117
// The wrapper must propagate --tenant onto every client it creates — this
// is what makes `stoactl get apis --tenant foo` actually scope the request
// to tenant "foo" instead of the context default.
func TestApplyTenantOverride_TenantFlagWins(t *testing.T) {
	defer reset()
	TenantOverride = "override-tenant"
	c := client.NewWithConfig("http://example", "ctx-default", "tok")

	applyTenantOverride(c)

	if got := c.TenantID(); got != "override-tenant" {
		t.Errorf("Client.TenantID() = %q, want %q", got, "override-tenant")
	}
}

// regression for CAB-2117
// When only --namespace is set on a non-bridge command the wrapper falls
// back to the deprecated alias so legacy scripts keep working during
// release N. The deprecation warning itself comes from the root PreRun
// hook, not from here.
func TestApplyTenantOverride_DeprecatedNamespaceAlias(t *testing.T) {
	defer reset()
	NamespaceOverride = "legacy-ns"
	c := client.NewWithConfig("http://example", "ctx-default", "tok")

	applyTenantOverride(c)

	if got := c.TenantID(); got != "legacy-ns" {
		t.Errorf("Client.TenantID() = %q, want %q (deprecated alias)", got, "legacy-ns")
	}
}

// regression for CAB-2117
// Without any CLI override the wrapper must leave the context-default tenant
// untouched — otherwise existing scripts that rely on `stoactl use-context`
// would silently lose their tenant scope.
func TestApplyTenantOverride_NoOverridePreservesContext(t *testing.T) {
	defer reset()
	c := client.NewWithConfig("http://example", "ctx-default", "tok")

	applyTenantOverride(c)

	if got := c.TenantID(); got != "ctx-default" {
		t.Errorf("Client.TenantID() = %q, want %q (context preserved)", got, "ctx-default")
	}
}

// regression for CAB-2117
// End-to-end: a client configured by the wrapper must actually send the
// overridden tenant in the X-Tenant-ID header of outgoing requests. This
// covers every non-bridge subcommand because they all go through the same
// helper + Client.do() pipeline.
func TestApplyTenantOverride_PropagatesInXTenantIDHeader(t *testing.T) {
	defer reset()

	var observed string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		observed = r.Header.Get("X-Tenant-ID")
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	TenantOverride = "override-tenant"
	c := client.NewWithConfig(srv.URL, "ctx-default", "tok")
	applyTenantOverride(c)

	resp, err := c.Do("GET", "/ping", nil)
	if err != nil {
		t.Fatalf("Do() err = %v", err)
	}
	_, _ = io.Copy(io.Discard, resp.Body)
	_ = resp.Body.Close()

	if observed != "override-tenant" {
		t.Errorf("X-Tenant-ID header = %q, want %q", observed, "override-tenant")
	}
}
