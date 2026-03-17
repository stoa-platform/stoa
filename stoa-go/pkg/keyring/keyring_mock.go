// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
package keyring

import "sync"

// MockKeyring implements TokenStore for testing without OS keychain access
type MockKeyring struct {
	mu    sync.RWMutex
	store map[string]*TokenData
}

// NewMockKeyring creates a new mock keyring
func NewMockKeyring() *MockKeyring {
	return &MockKeyring{
		store: make(map[string]*TokenData),
	}
}

// Set stores token data in memory
func (m *MockKeyring) Set(context string, data *TokenData) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.store[context] = data
	return nil
}

// Get retrieves token data from memory
func (m *MockKeyring) Get(context string) (*TokenData, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	data, ok := m.store[context]
	if !ok {
		return nil, nil
	}
	return data, nil
}

// Delete removes token data from memory
func (m *MockKeyring) Delete(context string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.store, context)
	return nil
}

// List returns all stored context names
func (m *MockKeyring) List() ([]string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	var names []string
	for name := range m.store {
		names = append(names, name)
	}
	return names, nil
}

// Name returns the storage backend name
func (m *MockKeyring) Name() string {
	return "Mock (in-memory)"
}
