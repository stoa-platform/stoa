// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package client

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// writeTestConfig stages a ~/.stoa/config file under the given HOME with a
// single "test" context set as current. The keychain is not touched; callers
// must drive token resolution via STOA_API_KEY / STOA_ADMIN_KEY env vars.
func writeTestConfig(t *testing.T, home string) {
	t.Helper()
	dir := filepath.Join(home, ".stoa")
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

func TestNewForMode_User_WithEnvToken(t *testing.T) {
	t.Setenv("HOME", t.TempDir())
	t.Setenv("STOA_API_KEY", "user-token-xyz")
	t.Setenv("STOA_ADMIN_KEY", "")
	writeTestConfig(t, os.Getenv("HOME"))

	c, err := NewForMode(false)
	if err != nil {
		t.Fatalf("NewForMode(false) error = %v, want nil", err)
	}
	if !c.IsAuthenticated() {
		t.Error("IsAuthenticated() = false, want true")
	}
	if c.TenantID() != "test-tenant" {
		t.Errorf("TenantID() = %q, want %q", c.TenantID(), "test-tenant")
	}
}

func TestNewForMode_Admin_WithEnvToken(t *testing.T) {
	t.Setenv("HOME", t.TempDir())
	t.Setenv("STOA_API_KEY", "")
	t.Setenv("STOA_ADMIN_KEY", "admin-sa-token-abc")
	writeTestConfig(t, os.Getenv("HOME"))

	c, err := NewForMode(true)
	if err != nil {
		t.Fatalf("NewForMode(true) error = %v, want nil", err)
	}
	if !c.IsAuthenticated() {
		t.Error("IsAuthenticated() = false, want true")
	}
}

func TestNewForMode_Admin_NoToken_ReturnsClearError(t *testing.T) {
	t.Setenv("HOME", t.TempDir())
	t.Setenv("STOA_API_KEY", "")
	t.Setenv("STOA_ADMIN_KEY", "")
	writeTestConfig(t, os.Getenv("HOME"))

	_, err := NewForMode(true)
	if err == nil {
		t.Fatal("NewForMode(true) error = nil, want error about missing admin token")
	}
	if !strings.Contains(err.Error(), "no admin token found") {
		t.Errorf("error = %q, want message containing 'no admin token found'", err.Error())
	}
}

func TestNewForMode_DispatchMatchesDirectCalls(t *testing.T) {
	t.Setenv("HOME", t.TempDir())
	t.Setenv("STOA_API_KEY", "user-token")
	t.Setenv("STOA_ADMIN_KEY", "admin-token")
	writeTestConfig(t, os.Getenv("HOME"))

	userViaMode, err := NewForMode(false)
	if err != nil {
		t.Fatalf("NewForMode(false): %v", err)
	}
	userDirect, err := New()
	if err != nil {
		t.Fatalf("New(): %v", err)
	}
	if userViaMode.GetBaseURL() != userDirect.GetBaseURL() {
		t.Errorf("NewForMode(false) and New() returned different base URLs: %q vs %q",
			userViaMode.GetBaseURL(), userDirect.GetBaseURL())
	}

	adminViaMode, err := NewForMode(true)
	if err != nil {
		t.Fatalf("NewForMode(true): %v", err)
	}
	adminDirect, err := NewAdmin()
	if err != nil {
		t.Fatalf("NewAdmin(): %v", err)
	}
	if adminViaMode.GetBaseURL() != adminDirect.GetBaseURL() {
		t.Errorf("NewForMode(true) and NewAdmin() returned different base URLs: %q vs %q",
			adminViaMode.GetBaseURL(), adminDirect.GetBaseURL())
	}
}
