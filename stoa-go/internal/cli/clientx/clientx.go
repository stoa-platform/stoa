// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM

// Package clientx wraps pkg/client construction with cobra-aware helpers so
// command packages can honor the persistent --admin flag uniformly.
package clientx

import (
	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/pkg/client"
)

// New returns a STOA API client scoped to the user OIDC token, or to the
// admin service-account token when the persistent --admin flag is set on
// the given command (or any of its ancestors). A nil cmd falls back to
// user-scope — useful in unit tests that exercise command handlers directly
// without a real cobra command tree.
func New(cmd *cobra.Command) (*client.Client, error) {
	var admin bool
	if cmd != nil {
		admin, _ = cmd.Flags().GetBool("admin")
	}
	return client.NewForMode(admin)
}
