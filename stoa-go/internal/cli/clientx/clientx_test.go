// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package clientx

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/spf13/cobra"
)

func writeTestStoaConfig(t *testing.T) {
	t.Helper()
	dir := filepath.Join(os.Getenv("HOME"), ".stoa")
	if err := os.MkdirAll(dir, 0700); err != nil {
		t.Fatalf("mkdir %s: %v", dir, err)
	}
	cfg := `apiVersion: stoa.io/v1
kind: Config
current-context: test
contexts:
  - name: test
    context:
      server: https://api.test.invalid
      tenant: test-tenant
`
	if err := os.WriteFile(filepath.Join(dir, "config"), []byte(cfg), 0600); err != nil {
		t.Fatalf("write config: %v", err)
	}
}

// newCmdWithAdminFlag builds a root-like *cobra.Command exposing the --admin
// persistent flag, mirroring the wiring in internal/cli/cmd/root.go.
func newCmdWithAdminFlag() *cobra.Command {
	root := &cobra.Command{Use: "stoactl-test"}
	var admin bool
	root.PersistentFlags().BoolVar(&admin, "admin", false, "admin mode")
	sub := &cobra.Command{Use: "sub", RunE: func(_ *cobra.Command, _ []string) error { return nil }}
	root.AddCommand(sub)
	return sub
}

func TestNew_FlagAbsent_UsesUserPath(t *testing.T) {
	t.Setenv("HOME", t.TempDir())
	t.Setenv("STOA_API_KEY", "user-tok")
	t.Setenv("STOA_ADMIN_KEY", "")
	writeTestStoaConfig(t)

	sub := newCmdWithAdminFlag()
	// Simulate invocation without --admin.
	sub.Root().SetArgs([]string{"sub"})
	if err := sub.Root().Execute(); err != nil {
		t.Fatalf("execute: %v", err)
	}

	c, err := New(sub)
	if err != nil {
		t.Fatalf("New() error = %v, want nil", err)
	}
	if !c.IsAuthenticated() {
		t.Error("IsAuthenticated() = false, want true")
	}
}

func TestNew_FlagSet_UsesAdminPath(t *testing.T) {
	t.Setenv("HOME", t.TempDir())
	t.Setenv("STOA_API_KEY", "")
	t.Setenv("STOA_ADMIN_KEY", "admin-tok")
	writeTestStoaConfig(t)

	sub := newCmdWithAdminFlag()
	sub.Root().SetArgs([]string{"sub", "--admin"})
	if err := sub.Root().Execute(); err != nil {
		t.Fatalf("execute: %v", err)
	}

	c, err := New(sub)
	if err != nil {
		t.Fatalf("New() error = %v, want nil", err)
	}
	if !c.IsAuthenticated() {
		t.Error("IsAuthenticated() = false, want true")
	}
}

func TestNew_AdminFlag_NoToken_ReturnsClearError(t *testing.T) {
	t.Setenv("HOME", t.TempDir())
	t.Setenv("STOA_API_KEY", "")
	t.Setenv("STOA_ADMIN_KEY", "")
	writeTestStoaConfig(t)

	sub := newCmdWithAdminFlag()
	sub.Root().SetArgs([]string{"sub", "--admin"})
	if err := sub.Root().Execute(); err != nil {
		t.Fatalf("execute: %v", err)
	}

	_, err := New(sub)
	if err == nil {
		t.Fatal("New() error = nil, want error about missing admin token")
	}
	if !strings.Contains(err.Error(), "no admin token found") {
		t.Errorf("error = %q, want message containing 'no admin token found'", err.Error())
	}
}
