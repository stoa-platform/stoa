// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package keyring

import (
	"encoding/json"
	"fmt"
	"time"

	gokeyring "github.com/zalando/go-keyring"
)

const (
	serviceName = "stoactl"
)

// TokenData represents token data stored in the keyring
type TokenData struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiresAt    int64  `json:"expires_at"`
	Context      string `json:"context"`
	StoredAt     int64  `json:"stored_at"`
}

// TokenStore abstracts secure token storage
type TokenStore interface {
	// Set stores a token for the given context
	Set(context string, data *TokenData) error
	// Get retrieves a token for the given context
	Get(context string) (*TokenData, error)
	// Delete removes a token for the given context
	Delete(context string) error
	// List returns all stored context names
	List() ([]string, error)
	// Name returns the storage backend name
	Name() string
}

// OSKeyring implements TokenStore using the OS keychain
type OSKeyring struct{}

// NewOSKeyring creates a new OS keyring store
func NewOSKeyring() *OSKeyring {
	return &OSKeyring{}
}

// Set stores token data in the OS keychain
func (k *OSKeyring) Set(context string, data *TokenData) error {
	data.StoredAt = time.Now().Unix()
	encoded, err := json.Marshal(data)
	if err != nil {
		return fmt.Errorf("failed to marshal token data: %w", err)
	}
	if err := gokeyring.Set(serviceName, context, string(encoded)); err != nil {
		return fmt.Errorf("failed to store in keychain: %w", err)
	}
	return nil
}

// Get retrieves token data from the OS keychain
func (k *OSKeyring) Get(context string) (*TokenData, error) {
	secret, err := gokeyring.Get(serviceName, context)
	if err != nil {
		if err == gokeyring.ErrNotFound {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to read from keychain: %w", err)
	}

	var data TokenData
	if err := json.Unmarshal([]byte(secret), &data); err != nil {
		return nil, fmt.Errorf("failed to parse keychain data: %w", err)
	}
	return &data, nil
}

// Delete removes token data from the OS keychain
func (k *OSKeyring) Delete(context string) error {
	err := gokeyring.Delete(serviceName, context)
	if err != nil && err != gokeyring.ErrNotFound {
		return fmt.Errorf("failed to delete from keychain: %w", err)
	}
	return nil
}

// List returns stored context names by checking known contexts from config
func (k *OSKeyring) List() ([]string, error) {
	// OS keychain doesn't support listing by service.
	// We return nil — callers should check specific contexts from config.
	return nil, nil
}

// Name returns the storage backend name
func (k *OSKeyring) Name() string {
	return "OS Keychain"
}

// Available checks if the OS keychain is accessible
func (k *OSKeyring) Available() bool {
	testKey := "__stoactl_probe__"
	err := gokeyring.Set(serviceName, testKey, "probe")
	if err != nil {
		return false
	}
	_ = gokeyring.Delete(serviceName, testKey)
	return true
}

// DefaultStore returns the default token store (OS keyring)
func DefaultStore() TokenStore {
	return NewOSKeyring()
}
