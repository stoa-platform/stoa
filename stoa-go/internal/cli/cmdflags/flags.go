// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM

// Package cmdflags holds persistent CLI flag state shared between root.go
// (which binds the flags) and subcommand packages (which read them).
// It exists because `internal/cli/cmd` imports every subcommand package for
// registration, so subcommands cannot import `cmd` back without creating an
// import cycle.
package cmdflags

// AdminMode indicates whether --admin was passed. Subcommands pass this to
// client.NewForMode to select between the user OIDC token and the service
// account token.
var AdminMode bool
