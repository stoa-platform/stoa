// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package config

import (
	"fmt"
	"os"
	"path/filepath"
	"time"

	"gopkg.in/yaml.v3"
)

// Config represents the stoactl configuration file
type Config struct {
	APIVersion     string    `yaml:"apiVersion"`
	Kind           string    `yaml:"kind"`
	CurrentContext string    `yaml:"current-context"`
	Contexts       []Context `yaml:"contexts"`
}

// Context represents a named context
type Context struct {
	Name    string        `yaml:"name"`
	Context ContextDetail `yaml:"context"`
}

// ContextDetail contains the context configuration
type ContextDetail struct {
	Server string `yaml:"server"`
	Tenant string `yaml:"tenant"`
}

// TokenCache stores OAuth tokens
type TokenCache struct {
	AccessToken  string `yaml:"access_token"`
	RefreshToken string `yaml:"refresh_token"`
	ExpiresAt    int64  `yaml:"expires_at"`
	Context      string `yaml:"context"`
}

// DefaultConfigPath returns the default config file path
func DefaultConfigPath() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return ".stoa/config"
	}
	return filepath.Join(home, ".stoa", "config")
}

// DefaultTokenPath returns the default token cache path
func DefaultTokenPath() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return ".stoa/tokens"
	}
	return filepath.Join(home, ".stoa", "tokens")
}

// Load loads the configuration from disk
func Load() (*Config, error) {
	path := DefaultConfigPath()

	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return &Config{
				APIVersion: "stoa.io/v1",
				Kind:       "Config",
				Contexts:   []Context{},
			}, nil
		}
		return nil, fmt.Errorf("failed to read config: %w", err)
	}

	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("failed to parse config: %w", err)
	}

	return &cfg, nil
}

// Save saves the configuration to disk
func (c *Config) Save() error {
	path := DefaultConfigPath()
	dir := filepath.Dir(path)

	if err := os.MkdirAll(dir, 0700); err != nil {
		return fmt.Errorf("failed to create config directory: %w", err)
	}

	data, err := yaml.Marshal(c)
	if err != nil {
		return fmt.Errorf("failed to marshal config: %w", err)
	}

	if err := os.WriteFile(path, data, 0600); err != nil {
		return fmt.Errorf("failed to write config: %w", err)
	}

	return nil
}

// GetCurrentContext returns the current context details
func (c *Config) GetCurrentContext() (*Context, error) {
	if c.CurrentContext == "" {
		return nil, fmt.Errorf("no current context set. Use 'stoactl config use-context <name>' to set one")
	}

	for _, ctx := range c.Contexts {
		if ctx.Name == c.CurrentContext {
			return &ctx, nil
		}
	}

	return nil, fmt.Errorf("context %q not found", c.CurrentContext)
}

// SetContext adds or updates a context
func (c *Config) SetContext(name, server, tenant string) {
	for i, ctx := range c.Contexts {
		if ctx.Name == name {
			c.Contexts[i].Context.Server = server
			c.Contexts[i].Context.Tenant = tenant
			return
		}
	}

	c.Contexts = append(c.Contexts, Context{
		Name: name,
		Context: ContextDetail{
			Server: server,
			Tenant: tenant,
		},
	})
}

// UseContext switches to the specified context
func (c *Config) UseContext(name string) error {
	for _, ctx := range c.Contexts {
		if ctx.Name == name {
			c.CurrentContext = name
			return nil
		}
	}
	return fmt.Errorf("context %q not found", name)
}

// LoadTokenCache loads the token cache
func LoadTokenCache() (*TokenCache, error) {
	path := DefaultTokenPath()

	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}

	var cache TokenCache
	if err := yaml.Unmarshal(data, &cache); err != nil {
		return nil, err
	}

	return &cache, nil
}

// SaveTokenCache saves the token cache
func SaveTokenCache(cache *TokenCache) error {
	path := DefaultTokenPath()
	dir := filepath.Dir(path)

	if err := os.MkdirAll(dir, 0700); err != nil {
		return err
	}

	data, err := yaml.Marshal(cache)
	if err != nil {
		return err
	}

	return os.WriteFile(path, data, 0600)
}

// DefaultAuditLogPath returns the audit log file path
func DefaultAuditLogPath() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return ".stoa/audit.log"
	}
	return filepath.Join(home, ".stoa", "audit.log")
}

// AppendAuditLog writes an entry to the audit log
func AppendAuditLog(operation, context, status string) error {
	path := DefaultAuditLogPath()
	dir := filepath.Dir(path)

	if err := os.MkdirAll(dir, 0700); err != nil {
		return fmt.Errorf("failed to create audit log directory: %w", err)
	}

	entry := fmt.Sprintf("%s | %s | context=%s | status=%s\n",
		time.Now().Format("2006-01-02T15:04"), operation, context, status)

	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0600)
	if err != nil {
		return fmt.Errorf("failed to open audit log: %w", err)
	}
	defer func() { _ = f.Close() }()

	_, err = f.WriteString(entry)
	return err
}
