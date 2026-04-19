// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package cmdflags

import (
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
