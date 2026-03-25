// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestDefaultConfigPath verifies the default config path format
func TestDefaultConfigPath(t *testing.T) {
	path := DefaultConfigPath()

	// Should contain .stoa/config
	if !strings.Contains(path, ".stoa") || !strings.Contains(path, "config") {
		t.Errorf("DefaultConfigPath() = %q, want path containing '.stoa' and 'config'", path)
	}
}

// TestDefaultTokenPath verifies the default token path format
func TestDefaultTokenPath(t *testing.T) {
	path := DefaultTokenPath()

	// Should contain .stoa/tokens
	if !strings.Contains(path, ".stoa") || !strings.Contains(path, "tokens") {
		t.Errorf("DefaultTokenPath() = %q, want path containing '.stoa' and 'tokens'", path)
	}
}

// TestConfigSetContext tests adding and updating contexts
func TestConfigSetContext(t *testing.T) {
	cfg := &Config{
		APIVersion: "stoa.io/v1",
		Kind:       "Config",
		Contexts:   []Context{},
	}

	// Test adding a new context
	cfg.SetContext("dev", "https://dev.stoa.io", "tenant-dev")

	if len(cfg.Contexts) != 1 {
		t.Fatalf("SetContext() contexts length = %d, want 1", len(cfg.Contexts))
	}

	if cfg.Contexts[0].Name != "dev" {
		t.Errorf("SetContext() name = %q, want %q", cfg.Contexts[0].Name, "dev")
	}
	if cfg.Contexts[0].Context.Server != "https://dev.stoa.io" {
		t.Errorf("SetContext() server = %q, want %q", cfg.Contexts[0].Context.Server, "https://dev.stoa.io")
	}
	if cfg.Contexts[0].Context.Tenant != "tenant-dev" {
		t.Errorf("SetContext() tenant = %q, want %q", cfg.Contexts[0].Context.Tenant, "tenant-dev")
	}

	// Test updating an existing context
	cfg.SetContext("dev", "https://dev2.stoa.io", "tenant-dev-updated")

	if len(cfg.Contexts) != 1 {
		t.Fatalf("SetContext() update should not add new context, got length %d", len(cfg.Contexts))
	}

	if cfg.Contexts[0].Context.Server != "https://dev2.stoa.io" {
		t.Errorf("SetContext() updated server = %q, want %q", cfg.Contexts[0].Context.Server, "https://dev2.stoa.io")
	}
	if cfg.Contexts[0].Context.Tenant != "tenant-dev-updated" {
		t.Errorf("SetContext() updated tenant = %q, want %q", cfg.Contexts[0].Context.Tenant, "tenant-dev-updated")
	}

	// Test adding a second context
	cfg.SetContext("prod", "https://prod.stoa.io", "tenant-prod")

	if len(cfg.Contexts) != 2 {
		t.Fatalf("SetContext() contexts length = %d, want 2", len(cfg.Contexts))
	}
}

// TestConfigUseContext tests switching contexts
func TestConfigUseContext(t *testing.T) {
	cfg := &Config{
		APIVersion: "stoa.io/v1",
		Kind:       "Config",
		Contexts: []Context{
			{Name: "dev", Context: ContextDetail{Server: "https://dev.stoa.io", Tenant: "dev-tenant"}},
			{Name: "prod", Context: ContextDetail{Server: "https://prod.stoa.io", Tenant: "prod-tenant"}},
		},
	}

	// Test switching to existing context
	err := cfg.UseContext("dev")
	if err != nil {
		t.Fatalf("UseContext() error = %v, want nil", err)
	}
	if cfg.CurrentContext != "dev" {
		t.Errorf("UseContext() CurrentContext = %q, want %q", cfg.CurrentContext, "dev")
	}

	// Test switching to another context
	err = cfg.UseContext("prod")
	if err != nil {
		t.Fatalf("UseContext() error = %v, want nil", err)
	}
	if cfg.CurrentContext != "prod" {
		t.Errorf("UseContext() CurrentContext = %q, want %q", cfg.CurrentContext, "prod")
	}

	// Test switching to non-existent context
	err = cfg.UseContext("nonexistent")
	if err == nil {
		t.Error("UseContext() error = nil, want error for nonexistent context")
	}
}

// TestConfigGetCurrentContext tests retrieving the current context
func TestConfigGetCurrentContext(t *testing.T) {
	tests := []struct {
		name            string
		cfg             *Config
		wantErr         bool
		wantContextName string
	}{
		{
			name: "valid current context",
			cfg: &Config{
				CurrentContext: "dev",
				Contexts: []Context{
					{Name: "dev", Context: ContextDetail{Server: "https://dev.stoa.io", Tenant: "dev-tenant"}},
				},
			},
			wantErr:         false,
			wantContextName: "dev",
		},
		{
			name: "no current context set",
			cfg: &Config{
				CurrentContext: "",
				Contexts: []Context{
					{Name: "dev", Context: ContextDetail{Server: "https://dev.stoa.io", Tenant: "dev-tenant"}},
				},
			},
			wantErr: true,
		},
		{
			name: "current context not found",
			cfg: &Config{
				CurrentContext: "nonexistent",
				Contexts: []Context{
					{Name: "dev", Context: ContextDetail{Server: "https://dev.stoa.io", Tenant: "dev-tenant"}},
				},
			},
			wantErr: true,
		},
		{
			name: "empty contexts list",
			cfg: &Config{
				CurrentContext: "dev",
				Contexts:       []Context{},
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			ctx, err := tt.cfg.GetCurrentContext()

			if tt.wantErr {
				if err == nil {
					t.Error("GetCurrentContext() error = nil, want error")
				}
				return
			}

			if err != nil {
				t.Fatalf("GetCurrentContext() error = %v, want nil", err)
			}

			if ctx.Name != tt.wantContextName {
				t.Errorf("GetCurrentContext() name = %q, want %q", ctx.Name, tt.wantContextName)
			}
		})
	}
}

// TestConfigSaveAndLoad tests saving and loading config with temp directory
func TestConfigSaveAndLoad(t *testing.T) {
	// Create a temporary directory
	tmpDir := t.TempDir()
	t.Setenv("HOME", tmpDir)

	// Create config to save
	cfg := &Config{
		APIVersion:     "stoa.io/v1",
		Kind:           "Config",
		CurrentContext: "test-context",
		Contexts: []Context{
			{
				Name: "test-context",
				Context: ContextDetail{
					Server: "https://test.stoa.io",
					Tenant: "test-tenant",
				},
			},
		},
	}

	// Save config
	err := cfg.Save()
	if err != nil {
		t.Fatalf("Save() error = %v", err)
	}

	// Verify file was created
	configPath := filepath.Join(tmpDir, ".stoa", "config")
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		t.Fatalf("Config file was not created at %s", configPath)
	}

	// Load config
	loadedCfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	// Verify loaded values
	if loadedCfg.APIVersion != cfg.APIVersion {
		t.Errorf("Load() APIVersion = %q, want %q", loadedCfg.APIVersion, cfg.APIVersion)
	}
	if loadedCfg.CurrentContext != cfg.CurrentContext {
		t.Errorf("Load() CurrentContext = %q, want %q", loadedCfg.CurrentContext, cfg.CurrentContext)
	}
	if len(loadedCfg.Contexts) != len(cfg.Contexts) {
		t.Errorf("Load() Contexts length = %d, want %d", len(loadedCfg.Contexts), len(cfg.Contexts))
	}
}

// TestLoadNonExistentConfig tests loading when config file doesn't exist
func TestLoadNonExistentConfig(t *testing.T) {
	// Create a temporary directory with no config file
	tmpDir := t.TempDir()
	t.Setenv("HOME", tmpDir)

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v, want nil for non-existent config", err)
	}

	// Should return empty config with defaults
	if cfg.APIVersion != "stoa.io/v1" {
		t.Errorf("Load() APIVersion = %q, want %q", cfg.APIVersion, "stoa.io/v1")
	}
	if cfg.Kind != "Config" {
		t.Errorf("Load() Kind = %q, want %q", cfg.Kind, "Config")
	}
	if len(cfg.Contexts) != 0 {
		t.Errorf("Load() Contexts length = %d, want 0", len(cfg.Contexts))
	}
}

// TestTokenCacheSaveAndLoad tests token cache operations
func TestTokenCacheSaveAndLoad(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("HOME", tmpDir)

	cache := &TokenCache{
		AccessToken:  "test-access-token",
		RefreshToken: "test-refresh-token",
		ExpiresAt:    1234567890,
		Context:      "test-context",
	}

	// Save token cache
	err := SaveTokenCache(cache)
	if err != nil {
		t.Fatalf("SaveTokenCache() error = %v", err)
	}

	// Load token cache
	loaded, err := LoadTokenCache()
	if err != nil {
		t.Fatalf("LoadTokenCache() error = %v", err)
	}

	if loaded.AccessToken != cache.AccessToken {
		t.Errorf("LoadTokenCache() AccessToken = %q, want %q", loaded.AccessToken, cache.AccessToken)
	}
	if loaded.RefreshToken != cache.RefreshToken {
		t.Errorf("LoadTokenCache() RefreshToken = %q, want %q", loaded.RefreshToken, cache.RefreshToken)
	}
	if loaded.ExpiresAt != cache.ExpiresAt {
		t.Errorf("LoadTokenCache() ExpiresAt = %d, want %d", loaded.ExpiresAt, cache.ExpiresAt)
	}
	if loaded.Context != cache.Context {
		t.Errorf("LoadTokenCache() Context = %q, want %q", loaded.Context, cache.Context)
	}
}

// TestLoadTokenCacheNonExistent tests loading when token cache doesn't exist
func TestLoadTokenCacheNonExistent(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("HOME", tmpDir)

	cache, err := LoadTokenCache()
	if err != nil {
		t.Fatalf("LoadTokenCache() error = %v, want nil", err)
	}
	if cache != nil {
		t.Errorf("LoadTokenCache() = %v, want nil for non-existent cache", cache)
	}
}
