// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package keyring

import (
	"testing"
	"time"
)

func TestMockKeyring_SetAndGet(t *testing.T) {
	store := NewMockKeyring()

	data := &TokenData{
		AccessToken:  "test-token",
		RefreshToken: "test-refresh",
		ExpiresAt:    time.Now().Add(time.Hour).Unix(),
		Context:      "prod",
	}

	if err := store.Set("prod", data); err != nil {
		t.Fatalf("Set failed: %v", err)
	}

	got, err := store.Get("prod")
	if err != nil {
		t.Fatalf("Get failed: %v", err)
	}
	if got == nil {
		t.Fatal("Get returned nil")
	}
	if got.AccessToken != "test-token" {
		t.Errorf("AccessToken = %q, want %q", got.AccessToken, "test-token")
	}
	if got.Context != "prod" {
		t.Errorf("Context = %q, want %q", got.Context, "prod")
	}
}

func TestMockKeyring_GetMissing(t *testing.T) {
	store := NewMockKeyring()

	got, err := store.Get("nonexistent")
	if err != nil {
		t.Fatalf("Get failed: %v", err)
	}
	if got != nil {
		t.Errorf("Get returned %v, want nil", got)
	}
}

func TestMockKeyring_Delete(t *testing.T) {
	store := NewMockKeyring()

	data := &TokenData{AccessToken: "token", Context: "test"}
	if err := store.Set("test", data); err != nil {
		t.Fatalf("Set failed: %v", err)
	}

	if err := store.Delete("test"); err != nil {
		t.Fatalf("Delete failed: %v", err)
	}

	got, err := store.Get("test")
	if err != nil {
		t.Fatalf("Get after delete failed: %v", err)
	}
	if got != nil {
		t.Error("Get after delete returned non-nil")
	}
}

func TestMockKeyring_DeleteMissing(t *testing.T) {
	store := NewMockKeyring()
	if err := store.Delete("nonexistent"); err != nil {
		t.Fatalf("Delete missing failed: %v", err)
	}
}

func TestMockKeyring_List(t *testing.T) {
	store := NewMockKeyring()

	_ = store.Set("prod", &TokenData{AccessToken: "a"})
	_ = store.Set("staging", &TokenData{AccessToken: "b"})

	names, err := store.List()
	if err != nil {
		t.Fatalf("List failed: %v", err)
	}
	if len(names) != 2 {
		t.Errorf("List returned %d items, want 2", len(names))
	}
}

func TestMockKeyring_Name(t *testing.T) {
	store := NewMockKeyring()
	if name := store.Name(); name != "Mock (in-memory)" {
		t.Errorf("Name = %q, want %q", name, "Mock (in-memory)")
	}
}

func TestOSKeyring_Name(t *testing.T) {
	store := NewOSKeyring()
	if name := store.Name(); name != "OS Keychain" {
		t.Errorf("Name = %q, want %q", name, "OS Keychain")
	}
}
