// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package cmdflags

import "github.com/stoa-platform/stoa-go/pkg/client"

// NewClientForMode constructs the CLI client honoring the --admin flag and
// applies the --tenant / STOACTL_TENANT override (or the deprecated
// --namespace alias) before returning.
//
// Every subcommand other than `stoactl bridge` should use this wrapper so
// that `--tenant` propagates end-to-end (both the `X-Tenant-ID` header and
// tenant-scoped paths). `bridge` must call client.NewForMode + SetTenantID
// explicitly because it treats --namespace as a K8s-only concept
// (namespaceIsDeprecated=false).
//
// The deprecation warning itself is emitted once per CLI invocation by the
// root PersistentPreRunE hook — this helper does NOT re-warn.
func NewClientForMode() (*client.Client, error) {
	c, err := client.NewForMode(AdminMode)
	if err != nil {
		return nil, err
	}
	applyTenantOverride(c)
	return c, nil
}

// NewAdminClient is the NewAdmin equivalent with tenant override support.
// Used by commands that always need the service-account token regardless of
// --admin (currently `catalog`).
func NewAdminClient() (*client.Client, error) {
	c, err := client.NewAdmin()
	if err != nil {
		return nil, err
	}
	applyTenantOverride(c)
	return c, nil
}

func applyTenantOverride(c *client.Client) {
	// Subcommands calling these helpers never keep --namespace as K8s scope
	// (bridge is the only exception and uses the raw client APIs). So the
	// deprecated-alias path is always active here.
	if t := ResolveTenant("", true); t != "" {
		c.SetTenantID(t)
	}
}
