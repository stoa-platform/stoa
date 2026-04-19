// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package cmd

import (
	"bytes"
	"os"
	"testing"

	"github.com/spf13/cobra"

	"github.com/stoa-platform/stoa-go/internal/cli/cmdflags"
)

func resetCmdflagsForRoot() {
	cmdflags.TenantOverride = ""
	cmdflags.NamespaceOverride = ""
	cmdflags.WarnStderr = os.Stderr
}

// regression for CAB-2117
// PersistentPreRunE warns once per CLI invocation when --namespace is used on
// a non-bridge command.
func TestWarnDeprecatedNamespaceIfNeeded_NonBridgeWarns(t *testing.T) {
	defer resetCmdflagsForRoot()

	var buf bytes.Buffer
	cmdflags.WarnStderr = &buf
	cmdflags.NamespaceOverride = "legacy"

	root := &cobra.Command{Use: "stoactl"}
	get := &cobra.Command{Use: "get"}
	apis := &cobra.Command{Use: "apis"}
	get.AddCommand(apis)
	root.AddCommand(get)

	if err := warnDeprecatedNamespaceIfNeeded(apis, nil); err != nil {
		t.Fatalf("hook returned err = %v", err)
	}

	want := "--namespace is deprecated for tenant scope on 'stoactl get apis', use --tenant\n"
	if buf.String() != want {
		t.Errorf("warning = %q, want %q", buf.String(), want)
	}
}

// regression for CAB-2117
// PersistentPreRunE is silent on `bridge` even when --namespace is set,
// because there --namespace keeps its original K8s semantic.
func TestWarnDeprecatedNamespaceIfNeeded_BridgeSilent(t *testing.T) {
	defer resetCmdflagsForRoot()

	var buf bytes.Buffer
	cmdflags.WarnStderr = &buf
	cmdflags.NamespaceOverride = "stoa-demo"

	root := &cobra.Command{Use: "stoactl"}
	bridge := &cobra.Command{Use: "bridge"}
	root.AddCommand(bridge)

	if err := warnDeprecatedNamespaceIfNeeded(bridge, nil); err != nil {
		t.Fatalf("hook returned err = %v", err)
	}
	if buf.Len() != 0 {
		t.Errorf("bridge must be silent; got %q", buf.String())
	}
}

// regression for CAB-2117
// No --namespace → no warning, regardless of subcommand.
func TestWarnDeprecatedNamespaceIfNeeded_NoFlagSilent(t *testing.T) {
	defer resetCmdflagsForRoot()

	var buf bytes.Buffer
	cmdflags.WarnStderr = &buf
	cmdflags.NamespaceOverride = ""
	cmdflags.TenantOverride = "modern"

	root := &cobra.Command{Use: "stoactl"}
	get := &cobra.Command{Use: "get"}
	root.AddCommand(get)

	if err := warnDeprecatedNamespaceIfNeeded(get, nil); err != nil {
		t.Fatalf("hook returned err = %v", err)
	}
	if buf.Len() != 0 {
		t.Errorf("expected silence with --tenant; got %q", buf.String())
	}
}
