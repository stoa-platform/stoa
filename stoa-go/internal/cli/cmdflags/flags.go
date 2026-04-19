// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM

// Package cmdflags holds persistent CLI flag state shared between root.go
// (which binds the flags) and subcommand packages (which read them).
// It exists because `internal/cli/cmd` imports every subcommand package for
// registration, so subcommands cannot import `cmd` back without creating an
// import cycle.
package cmdflags

import (
	"fmt"
	"io"
	"os"
)

// Contract strings for the --tenant / --namespace split (CAB-2117). Kept as
// constants so tests and the root PreRun hook use the exact same values.
const (
	// deprecationWarningFormat is the stderr template emitted whenever
	// --namespace is consumed as a tenant alias outside of `bridge`.
	deprecationWarningFormat = "--namespace is deprecated for tenant scope on 'stoactl %s', use --tenant\n"
	// genericCmdPlaceholder is the fallback rendered when the caller does
	// not know (or cannot supply) the leaf subcommand name.
	genericCmdPlaceholder = "<cmd>"
	// StoactlBinaryName is the program name; exposed so the root PreRun
	// hook can trim it off `cobra.Command.CommandPath()` without
	// hard-coding the string at two sites.
	StoactlBinaryName = "stoactl"
	// BridgeCommandName is the one subcommand where --namespace keeps its
	// K8s semantic and the deprecation warning is suppressed.
	BridgeCommandName = "bridge"
)

// AdminMode indicates whether --admin was passed. Subcommands pass this to
// client.NewForMode to select between the user OIDC token and the service
// account token.
var AdminMode bool

// TenantOverride holds the value of the persistent --tenant flag (or the
// STOACTL_TENANT env var default). When non-empty, commands use this as the
// CP-API tenant scope, taking precedence over metadata.namespace and the
// configured context tenant.
var TenantOverride string

// NamespaceOverride holds the value of the persistent --namespace flag (or
// the STOACTL_NAMESPACE env var default).
//
// Semantics depend on the command:
//   - bridge: K8s namespace for generated Tool CRDs (metadata.namespace).
//     This is the non-deprecated use.
//   - every other command: legacy tenant alias (deprecated for tenant scope).
//     Callers must invoke WarnDeprecatedNamespace on first read.
var NamespaceOverride string

// WarnStderr is the sink for deprecation warnings. Tests override it.
var WarnStderr io.Writer = os.Stderr

// WarnDeprecatedNamespace emits the deterministic stderr deprecation warning
// used when --namespace (or STOACTL_NAMESPACE) is read as a tenant scope
// outside of the bridge command. The message format is contract; the exact
// wording is part of the acceptance criteria of CAB-2117.
//
// cmdName should be the leaf subcommand name (e.g. "apply", "get", "delete").
// Callers on the root itself can pass an empty string to get a generic
// message.
func WarnDeprecatedNamespace(cmdName string) {
	target := cmdName
	if target == "" {
		target = genericCmdPlaceholder
	}
	_, _ = fmt.Fprintf(WarnStderr, deprecationWarningFormat, target)
}

// ResolveTenant returns the effective CP tenant using the precedence order
// documented in CAB-2117:
//
//  1. --tenant flag / STOACTL_TENANT env var (TenantOverride)
//  2. --namespace flag / STOACTL_NAMESPACE env var (NamespaceOverride) —
//     deprecated tenant alias. The deprecation warning itself is emitted
//     once per CLI invocation by the root PersistentPreRun hook, NOT here,
//     so multiple call sites within the same subcommand do not produce
//     duplicate warnings.
//  3. empty string (caller should fall through to manifest / config).
//
// namespaceIsDeprecated must be false in contexts where --namespace keeps its
// original K8s meaning (i.e. `bridge`). The legacy alias path is then
// skipped — that command must consume NamespaceOverride directly with its
// K8s semantics.
func ResolveTenant(_ string, namespaceIsDeprecated bool) string {
	if TenantOverride != "" {
		return TenantOverride
	}
	if namespaceIsDeprecated && NamespaceOverride != "" {
		return NamespaceOverride
	}
	return ""
}
