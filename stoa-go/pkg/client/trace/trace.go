// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM

// Package trace provides distributed trace query operations for stoactl.
// Implementation comes in Phase 2 (CAB-2023).
package trace

import "net/http"

// Doer performs HTTP requests. Satisfied by *client.Client.
type Doer interface {
	Do(method, path string, body any) (*http.Response, error)
}

// Service provides trace query operations.
type Service struct {
	doer Doer
}

// New creates a trace service backed by the given HTTP doer.
func New(doer Doer) *Service {
	return &Service{doer: doer}
}
